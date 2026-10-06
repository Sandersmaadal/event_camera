#!/usr/bin/env python3
"""Step 3: look at every static pose and accept or reject it.

    python review.py sessions/tv01              # go through all poses
    python review.py sessions/tv01 --flagged    # only the suspicious ones
    python review.py sessions/tv01 --export out # save the panels as PNG, no window

Each panel shows the accumulated flip image of the left and right camera with
the detected corners drawn on top. Corner 0 is marked with a circle and the
corners are joined in order, so a wrong grid or a reversed order is obvious.

Keys (click the window first):
    a / space   accept both cameras and go on
    r           reject both cameras and go on
    1           reject left, keep right, go on   2   reject right, keep left, go on
    b           back                             f   jump to the next flagged pose
    q / Esc     save and quit

Your eye is good at spotting gross failures (wrong grid, corners on the TV
frame, a smeared image). It cannot see a 0.3 px error, so the numbers under
each image matter more: "scatter" is how much the corners moved between the
flips of this pose, and "reproj" is the reprojection error of this view in a
quick calibration of all views. Poses where either is high are flagged in red.
Poses you never look at count as accepted.
"""
import argparse
import os

import cv2
import numpy as np

from evcalib import board, calib, session
from evcalib import settings as S

ROW_COLOURS = [(60, 60, 230), (40, 150, 240), (40, 200, 200), (70, 190, 70), (220, 150, 40), (200, 70, 160)]


def quick_errors(meta):
    """Per-view reprojection error from a calibration of all views, per camera."""
    cols, rows, size = meta["cols"], meta["rows"], (meta["width"], meta["height"])
    w = S.SQUARE_W_MM or 1.0
    obj = calib.object_points(cols, rows, w, S.SQUARE_H_MM or w)
    errs = {}
    for side in meta["sides"]:
        ids = [v["id"] for v in meta["views"] if side in v]
        if len(ids) < 6:
            continue
        res = calib.calibrate_mono([session.corners(meta["views"][i], side) for i in ids],
                                   obj, size, reject=False)
        for k, e in res["view_err"].items():
            errs[(ids[k], side)] = e
        errs[(side, "limit")] = max(0.3, 2.5 * float(np.median(list(res["view_err"].values()))))
    return errs


def flags(view, side, errs):
    """Reasons why this camera's view deserves a closer look."""
    out = []
    if side not in view:
        return out
    if view[side]["scatter_px"] > S.MAX_POSE_SCATTER_PX:
        out.append("scatter")
    if view[side]["n_flips"] <= S.MIN_FLIPS_PER_POSE:
        out.append("few flips")
    e = errs.get((view["id"], side))
    if e is not None and e > errs.get((side, "limit"), 1e9):
        out.append("reproj")
    if view[side]["source"] != "accumulated":
        out.append("board not found in the summed image")
    return out


def draw_side(frame, view, side, errs, scale, decision):
    h, w = frame.shape
    img = cv2.resize(board.render(frame), (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    bar = np.full((64, w * scale, 3), 30, np.uint8)
    if side not in view:
        cv2.putText(img, "board not found in this camera", (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(bar, side.upper(), (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1, cv2.LINE_AA)
        return np.vstack([img, bar])
    c = (session.corners(view, side) + 0.5) * scale - 0.5
    cols = len(c) // len(ROW_COLOURS) if len(c) % len(ROW_COLOURS) == 0 else S.BOARD_COLS
    pts = np.round(c * 8).astype(np.int32)                       # 1/8 pixel drawing precision
    for i in range(len(c) - 1):
        cv2.line(img, tuple(pts[i]), tuple(pts[i + 1]), ROW_COLOURS[(i // cols) % len(ROW_COLOURS)],
                 1, cv2.LINE_AA, shift=3)
    for i, p in enumerate(pts):
        col = ROW_COLOURS[(i // cols) % len(ROW_COLOURS)]
        cv2.drawMarker(img, (int(p[0] // 8), int(p[1] // 8)), col, cv2.MARKER_TILTED_CROSS, 7, 1, cv2.LINE_AA)
    cv2.circle(img, tuple(pts[0]), 9 * 8, (0, 0, 255), 2, cv2.LINE_AA, shift=3)
    cv2.putText(img, "0", (int(pts[0][0] // 8) + 12, int(pts[0][1] // 8) - 8), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (0, 0, 255), 2, cv2.LINE_AA)

    why = flags(view, side, errs)
    e = errs.get((view["id"], side))
    info = (f"{side.upper()}  flips {view[side]['n_flips']}   scatter {view[side]['scatter_px']:.2f} px   "
            f"reproj {'%.2f px' % e if e is not None else 'n/a'}")
    cv2.putText(bar, info, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (80, 80, 255) if why else (220, 220, 220), 1, cv2.LINE_AA)
    state = {True: ("ACCEPTED", (90, 220, 90)), False: ("REJECTED", (80, 80, 255)),
             None: ("not reviewed", (170, 170, 170))}[decision]
    cv2.putText(bar, state[0] + ("   flagged: " + ", ".join(why) if why else ""), (8, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, state[1], 1, cv2.LINE_AA)
    return np.vstack([img, bar])


def panel(meta, frames, view, errs, review, scale, position):
    parts = []
    for side in meta["sides"]:
        decision = review.get(str(view["id"]), {}).get(side) if side in view else None
        parts.append(draw_side(frames[side][view["id"]], view, side, errs, scale, decision))
    img = np.hstack(parts)
    head = np.full((34, img.shape[1], 3), 30, np.uint8)
    cv2.putText(head, f"pose {view['id']}  ({position})   t = {view['t_start'] / 1e6:.1f} s   "
                "a accept | r reject | 1 reject left | 2 reject right | b back | f next flagged | q quit",
                (8, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA)
    return np.vstack([head, img])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--flagged", action="store_true", help="show only poses that look suspicious")
    ap.add_argument("--scale", type=int, default=2, help="image zoom (default 2)")
    ap.add_argument("--export", metavar="DIR", help="write the panels as PNG files instead of opening a window")
    args = ap.parse_args()

    meta = session.load_views(args.session)
    views = meta["views"]
    data = np.load(os.path.join(args.session, "views_frames.npz"))
    frames = {s: data[f"acc_{s}"] for s in meta["sides"]}
    review = session.load_review(args.session)
    errs = quick_errors(meta)

    def is_flagged(v):
        return any(flags(v, s, errs) for s in meta["sides"])

    order = [v["id"] for v in views if not args.flagged or is_flagged(v)]
    n_flag = sum(is_flagged(v) for v in views)
    print(f"{len(views)} poses, {n_flag} flagged, {len(review)} already reviewed.")
    if not order:
        print("Nothing to show.")
        return

    if args.export:
        os.makedirs(args.export, exist_ok=True)
        for k, vid in enumerate(order):
            img = panel(meta, frames, views[vid], errs, review, args.scale, f"{k + 1} of {len(order)}")
            cv2.imwrite(os.path.join(args.export, f"pose_{vid:03d}.png"), img)
        print(f"Wrote {len(order)} panels to {args.export}")
        return

    def decide(view, left, right):
        entry = review.get(str(view["id"]), {})
        for side, val in (("left", left), ("right", right)):
            if side in view and val is not None:
                entry[side] = val
        review[str(view["id"])] = entry
        session.save_review(args.session, review)

    k = 0
    win = "review"
    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    while 0 <= k < len(order):
        view = views[order[k]]
        cv2.imshow(win, panel(meta, frames, view, errs, review, args.scale, f"{k + 1} of {len(order)}"))
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key in (ord("a"), ord("y"), ord(" ")):
            decide(view, True, True)
            k += 1
        elif key in (ord("r"), ord("n"), ord("x")):
            decide(view, False, False)
            k += 1
        elif key == ord("1"):
            decide(view, False, True)
            k += 1
        elif key == ord("2"):
            decide(view, True, False)
            k += 1
        elif key == ord("b"):
            k = max(0, k - 1)
        elif key == ord("f"):
            nxt = next((j for j in range(k + 1, len(order)) if is_flagged(views[order[j]])), None)
            k = nxt if nxt is not None else k
    cv2.destroyAllWindows()
    session.save_review(args.session, review)
    n_rej = sum(1 for e in review.values() if not all(e.values()))
    print(f"Saved review.json: {len(review)} poses reviewed, {n_rej} with a rejection.")
    print(f"Next: python calibrate.py {args.session} --square-mm <measured size>")


if __name__ == "__main__":
    main()
