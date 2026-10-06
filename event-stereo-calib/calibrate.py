#!/usr/bin/env python3
"""Step 4: calibrate both cameras and the stereo pair from a session.

    python calibrate.py sessions/tv01 --square-mm 68.5
    python calibrate.py sessions/tv01 --square-mm 68.5 --out ~/Master_thesis_project/config

Uses every static pose from detect.py that was not rejected in review.py.
Writes camera_left.json, camera_right.json and stereo_params.json in the
layout that the depth, rectification and tracking scripts of
yug3nn/Master_thesis_project read: K as 3x3, D as 1x5, R and T at the top
level, T in millimetres.
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np

from evcalib import calib, session
from evcalib import settings as S


def save_coverage(path, points, size):
    w, h = size
    scale = 3
    img = np.full((h * scale, w * scale, 3), 255, np.uint8)
    for p in points:
        for x, y in np.asarray(p).reshape(-1, 2):
            cv2.circle(img, (int(x * scale), int(y * scale)), 2, (160, 90, 30), -1, cv2.LINE_AA)
    cv2.imwrite(path, img)


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--square-mm", type=float, nargs="+", metavar="MM",
                    help="measured square size on the screen: one value, or width and height")
    ap.add_argument("--out", help="also copy the three JSON files to this folder")
    ap.add_argument("--no-reject", action="store_true", help="keep all views, no outlier rejection")
    args = ap.parse_args()

    if args.square_mm:
        sw, sh = args.square_mm[0], args.square_mm[-1]
    elif S.SQUARE_W_MM:
        sw, sh = S.SQUARE_W_MM, S.SQUARE_H_MM or S.SQUARE_W_MM
    else:
        sys.exit("The square size is not set. Measure the board on the screen (total width / 10 and "
                 "total height / 7, in mm) and pass --square-mm, or set SQUARE_W_MM in evcalib/settings.py.")

    meta = session.load_views(args.session)
    review = session.load_review(args.session)
    cols, rows, size = meta["cols"], meta["rows"], (meta["width"], meta["height"])
    views = meta["views"]
    obj = calib.object_points(cols, rows, sw, sh)
    out_dir = os.path.join(args.session, "config")
    os.makedirs(out_dir, exist_ok=True)
    lines = []

    def say(text=""):
        print(text)
        lines.append(text)

    say(f"Session {args.session}: {len(views)} static poses, {len(review)} reviewed, "
        f"square {sw:g} x {sh:g} mm")
    if abs(sw - sh) > 0.02 * sw:
        say("NOTE: the squares are not square. Check the TV's picture size setting (it should show "
            "the image 1:1, not zoomed or stretched).")

    # --- intrinsics ----------------------------------------------------------
    mono = {}
    for side in meta["sides"]:
        ids = [v["id"] for v in views if session.usable(v, side, review)]
        if len(ids) < 8:
            say(f"\n{side.upper()}: only {len(ids)} usable views, cannot calibrate (need at least 8, "
                f"{S.MIN_VIEWS}+ recommended).")
            continue
        pts = [session.corners(views[i], side) for i in ids]
        res = calib.calibrate_mono(pts, obj, size, reject=not args.no_reject)
        res["ids"] = [ids[k] for k in res["keep"]]
        mono[side] = res
        K, D = res["K"], res["D"]
        cov = calib.coverage([pts[k] for k in res["keep"]], size)
        say(f"\n{side.upper()} camera")
        say(f"  views used      : {len(res['keep'])} of {res['n_in']}"
            + (f"  (rejected ids: {sorted(set(ids) - set(res['ids']))})" if len(res["keep"]) < res["n_in"] else ""))
        say(f"  RMS reprojection: {res['rms']:.3f} px")
        std = res["std_fx_fy_cx_cy"]
        say(f"  fx, fy          : {K[0, 0]:.2f} +/- {std[0]:.2f}, {K[1, 1]:.2f} +/- {std[1]:.2f} px")
        say(f"  cx, cy          : {K[0, 2]:.2f} +/- {std[2]:.2f}, {K[1, 2]:.2f} +/- {std[3]:.2f} px")
        say(f"  distortion      : {np.array2string(D.ravel(), precision=4, suppress_small=True)}")
        say(f"  image coverage  : {int((cov > 0).sum())} of {cov.size} cells have corners")
        if len(res["keep"]) < S.MIN_VIEWS:
            say(f"  WARNING: fewer than {S.MIN_VIEWS} views. Record more poses.")
        if (cov > 0).mean() < 0.8:
            say("  WARNING: parts of the image never saw the board, so the distortion there is a guess. "
                "Record poses with the board near the image edges and corners (see coverage_*.png).")
        if res["rms"] > 0.5:
            say("  WARNING: RMS above 0.5 px. Reject the worst views in review.py and check focus.")
        save_coverage(os.path.join(out_dir, f"coverage_{side}.png"), [pts[k] for k in res["keep"]], size)
        write_json(os.path.join(out_dir, f"camera_{side}.json"), {
            "type": "pinhole", "width": size[0], "height": size[1],
            "K": K.tolist(), "D": D.tolist(), "RMS": res["rms"], "n_images_used": len(res["keep"])})

    # --- stereo --------------------------------------------------------------
    if "left" in mono and "right" in mono:
        good = {s: set(mono[s]["ids"]) for s in session.SIDES}
        ids = [v["id"] for v in views if v["id"] in good["left"] and v["id"] in good["right"]]
        say("\nSTEREO")
        if len(ids) < 8:
            say(f"  only {len(ids)} poses were seen by both cameras, cannot calibrate the pair.")
        else:
            pl = [session.corners(views[i], "left") for i in ids]
            pr = [session.corners(views[i], "right") for i in ids]
            KL, DL, KR, DR = mono["left"]["K"], mono["left"]["D"], mono["right"]["K"], mono["right"]["D"]
            st = calib.calibrate_stereo(pl, pr, obj, size, KL, DL, KR, DR, reject=not args.no_reject)
            # The corner order is chosen per image. If one camera is mounted
            # upside down relative to the other, its order is reversed.
            pr_rev = [p[::-1] for p in pr]
            st_rev = calib.calibrate_stereo(pl, pr_rev, obj, size, KL, DL, KR, DR, reject=False)
            if st_rev["rms"] < 0.5 * st["rms"]:
                say("  NOTE: the right camera looks rotated 180 degrees relative to the left one; "
                    "its corner order was reversed to match.")
                pr = pr_rev
                st = calib.calibrate_stereo(pl, pr, obj, size, KL, DL, KR, DR, reject=not args.no_reject)
            kept = st["keep"]
            m = calib.stereo_metrics([pl[k] for k in kept], [pr[k] for k in kept], cols, rows, sw, sh,
                                     size, KL, DL, KR, DR, st["R"], st["T"])
            angle = np.degrees(np.linalg.norm(cv2.Rodrigues(st["R"])[0]))
            say(f"  views used      : {len(kept)} of {st['n_in']}"
                + (f"  (rejected ids: {sorted(set(ids) - {ids[k] for k in kept})})" if len(kept) < st["n_in"] else ""))
            say(f"  RMS reprojection: {st['rms']:.3f} px")
            say(f"  baseline        : {m['baseline_mm']:.2f} mm   <- compare with a ruler measurement")
            say(f"  T (mm)          : {np.array2string(st['T'].ravel(), precision=2)}")
            say(f"  rotation L->R   : {angle:.2f} deg")
            say(f"  epipolar error  : mean {m['epipolar_mean_px']:.3f} px, 95% below {m['epipolar_p95_px']:.3f} px")
            say(f"  square size     : median error {m['square_median_err_mm']:.2f} mm, "
                f"mean {m['square_mean_err_mm']:.2f} mm (triangulated vs measured)")
            say(f"  board distances : {m['depth_min_mm']:.0f} to {m['depth_max_mm']:.0f} mm")
            if m["epipolar_mean_px"] > 0.3:
                say("  WARNING: epipolar error above 0.3 px. Depth from this calibration will be poor.")
            write_json(os.path.join(out_dir, "stereo_params.json"), {
                "R": st["R"].tolist(), "T": st["T"].tolist(), "E": st["E"].tolist(), "F": st["F"].tolist(),
                "RMS": st["rms"], "Metric_Median_mm": m["square_median_err_mm"],
                "Metric_MAE_mm": m["square_mean_err_mm"], "n_images_used": st["n_in"],
                "n_images_kept": len(kept), "baseline_mm": m["baseline_mm"],
                "epipolar_mean_px": m["epipolar_mean_px"], "units": "mm",
                "square_w_mm": sw, "square_h_mm": sh,
                "R1": m["R1"].tolist(), "R2": m["R2"].tolist(), "P1": m["P1"].tolist(),
                "P2": m["P2"].tolist(), "Q": m["Q"].tolist()})

    with open(os.path.join(out_dir, "report.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    say(f"\nResults written to {out_dir}")
    if args.out:
        dst = os.path.expanduser(args.out)
        os.makedirs(dst, exist_ok=True)
        for name in ("camera_left.json", "camera_right.json", "stereo_params.json"):
            src = os.path.join(out_dir, name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(dst, name))
        print(f"Copied the JSON files to {dst}")


if __name__ == "__main__":
    main()
