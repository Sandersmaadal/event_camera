#!/usr/bin/env python3
"""Semi-dense depth from a stereo event recording.

    python depth.py sessions/lab01 --config ../event-stereo-calib/sessions/tv01/config
    python depth.py /media/.../test01 --config <config> --preview
    python depth.py sessions/lab01 --config <config> --roi 140 120 180 160

The recording is either a folder with left.npz and right.npz (or left.raw and
right.raw), or the prefix that record_all writes (<prefix>_left.raw and
<prefix>_right.raw). Converting .raw needs the Metavision SDK; .npz does not.

Every --step-ms the last --window-ms of events from each camera is rectified,
turned into an image (--repr) and matched along rows. Results go to
<out>/depth.npz as one row per matched pixel, and with --preview to a PNG per
step showing both rectified images and the depth map.

--roi x0 y0 x1 y1 (rectified left image coordinates) prints the median depth
inside that box for every step, for comparing with a tape-measured target.
"""
import argparse
import os
import sys
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "event-stereo-calib"))
from evcalib.events import load_events  # noqa: E402

from evdepth.matching import MatchParams, match  # noqa: E402
from evdepth.rectify import StereoCalib, make_rectifiers  # noqa: E402
from evdepth.representation import event_count, make_image  # noqa: E402


def find_inputs(path):
    """(left file, right file) for a session folder or a record_all prefix."""
    candidates = []
    if os.path.isdir(path):
        for ext in (".npz", ".raw", ".hdf5"):
            candidates.append((os.path.join(path, "left" + ext), os.path.join(path, "right" + ext)))
    for ext in (".npz", ".raw", ".hdf5"):
        candidates.append((f"{path}_left{ext}", f"{path}_right{ext}"))
    for left, right in candidates:
        if os.path.exists(left) and os.path.exists(right):
            return left, right
    raise SystemExit(f"No left/right recording found for {path}. Expected left.npz and right.npz in a "
                     "folder, or <prefix>_left.raw and <prefix>_right.raw.")


def rectify_window(ev, rect, i0, i1):
    x, y, t = ev.x[i0:i1], ev.y[i0:i1], ev.t[i0:i1]
    xr, yr, inside = rect(x, y)
    return xr[inside], yr[inside], t[inside]


def to_display(img):
    m = np.percentile(img, 99.5) if img.any() else 1.0
    return cv2.cvtColor(np.clip(img / max(m, 1e-6) * 255, 0, 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


def preview(path, left_img, right_img, depth_m, zmin, zmax, t_s, n_valid, scale=2):
    a, b = to_display(left_img), to_display(right_img)
    for y in range(0, a.shape[0], 20):   # rows to check rectification by eye
        cv2.line(a, (0, y), (a.shape[1], y), (0, 90, 0), 1)
        cv2.line(b, (0, y), (b.shape[1], y), (0, 90, 0), 1)
    valid = np.isfinite(depth_m)
    norm = np.zeros(depth_m.shape, np.uint8)
    norm[valid] = np.clip((depth_m[valid] - zmin) / (zmax - zmin) * 255, 0, 255).astype(np.uint8)
    c = cv2.applyColorMap(255 - norm, cv2.COLORMAP_TURBO)   # red = near, blue = far
    c[~valid] = 0
    # Dilate the sparse points a little so they are visible.
    c = cv2.dilate(c, np.ones((2, 2), np.uint8))
    out = cv2.resize(np.hstack([a, b, c]), None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    w = a.shape[1] * scale
    for i, label in enumerate(("left (rectified)", "right (rectified)",
                               f"depth {zmin:.1f}-{zmax:.1f} m, {n_valid} px")):
        cv2.putText(out, label, (i * w + 8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(out, f"t = {t_s:.3f} s", (8, out.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(path, out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="folder with left/right files, or a record_all prefix")
    ap.add_argument("--config", required=True, help="folder with camera_left.json, camera_right.json, "
                                                    "stereo_params.json")
    ap.add_argument("--out", help="output folder (default: <recording>_depth)")
    ap.add_argument("--repr", choices=("ts", "count"), default="count", help="event representation")
    ap.add_argument("--window-ms", type=float, default=20.0, help="events used per depth estimate")
    ap.add_argument("--tau-ms", type=float, default=None, help="time-surface decay (default: window / 2)")
    ap.add_argument("--step-ms", type=float, default=50.0, help="time between depth estimates")
    ap.add_argument("--start-s", type=float, default=0.0, help="skip this much of the recording")
    ap.add_argument("--duration-s", type=float, default=None, help="process only this much")
    ap.add_argument("--right-offset-us", type=int, default=0,
                    help="added to right timestamps, only if the cameras were not hardware synced")
    ap.add_argument("--min-disp", type=int, default=MatchParams.min_disp)
    ap.add_argument("--max-disp", type=int, default=MatchParams.max_disp)
    ap.add_argument("--patch", type=int, default=MatchParams.patch)
    ap.add_argument("--min-events", type=int, default=MatchParams.min_events)
    ap.add_argument("--min-score", type=float, default=MatchParams.min_score)
    ap.add_argument("--min-margin", type=float, default=MatchParams.min_margin)
    ap.add_argument("--roi", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                    help="print median depth in this box of the rectified left image")
    ap.add_argument("--preview", action="store_true", help="write a PNG per step")
    ap.add_argument("--zrange", type=float, nargs=2, metavar=("ZMIN", "ZMAX"),
                    help="depth range of the preview colours, metres (default: from the data)")
    args = ap.parse_args()

    if args.patch % 2 == 0:
        sys.exit("--patch must be odd")
    params = MatchParams(args.min_disp, args.max_disp, args.patch, args.min_events,
                         args.min_score, args.min_margin)
    window_us = int(args.window_ms * 1000)
    tau_us = (args.tau_ms * 1000) if args.tau_ms else window_us / 2
    step_us = int(args.step_ms * 1000)

    calib = StereoCalib(args.config)
    rect_l, rect_r = make_rectifiers(calib)
    sign = calib.disparity_sign
    print(f"Calibration: f = {calib.focal_px:.1f} px, baseline = {calib.baseline_mm:.1f} mm, "
          f"{calib.width} x {calib.height}")
    if sign < 0:
        print("NOTE: the camera called 'left' is to the right of the other one. Disparities are "
              "searched the other way; depth is unaffected.")
    near = calib.depth_from_disparity(max(params.max_disp - 1, 1))
    far = calib.depth_from_disparity(max(params.min_disp, 1))
    print(f"Disparities {params.min_disp}..{params.max_disp - 1} px cover {near:.2f} m to "
          f"{'infinity' if params.min_disp == 0 else f'{far:.2f} m'}. One pixel of disparity error is "
          f"{calib.depth_error_per_px(1.0):.3f} m at 1 m, {calib.depth_error_per_px(5.0):.2f} m at 5 m, "
          f"{calib.depth_error_per_px(10.0):.2f} m at 10 m.")

    left_file, right_file = find_inputs(args.recording.rstrip("/"))
    print(f"Loading {left_file} and {right_file} ...")
    ev_l, ev_r = load_events(left_file), load_events(right_file)
    if (ev_l.width, ev_l.height) != (calib.width, calib.height):
        sys.exit(f"Recording is {ev_l.width} x {ev_l.height} but the calibration is "
                 f"{calib.width} x {calib.height}.")
    if args.right_offset_us:
        ev_r.t = ev_r.t + args.right_offset_us
    if len(ev_l) == 0 or len(ev_r) == 0:
        sys.exit("One of the recordings has no events.")

    t0 = max(ev_l.t[0], ev_r.t[0]) + int(args.start_s * 1e6)
    t_end = min(ev_l.t[-1], ev_r.t[-1])
    if args.duration_s:
        t_end = min(t_end, t0 + int(args.duration_s * 1e6))
    if t0 + window_us > t_end:
        sys.exit("The recordings do not overlap long enough in time. Are they from the same session, "
                 "and was hardware sync on?")
    times = np.arange(t0 + window_us, t_end + 1, step_us)
    print(f"{len(times)} steps of {args.step_ms:g} ms, window {args.window_ms:g} ms, repr '{args.repr}', "
          f"tau {tau_us / 1000:g} ms")

    out_dir = args.out or (args.recording.rstrip("/") + "_depth")
    os.makedirs(out_dir, exist_ok=True)
    if args.preview:
        os.makedirs(os.path.join(out_dir, "preview"), exist_ok=True)

    rows = {"frame": [], "x": [], "y": [], "disparity": [], "depth_m": [], "score": [], "margin": []}
    roi_log = []
    stats = {"support": 0, "score": 0, "unique": 0, "lr": 0, "kept": 0}
    zrange = args.zrange
    tic = time.time()
    for k, t_ref in enumerate(times):
        imgs, counts = [], []
        for ev, rect in ((ev_l, rect_l), (ev_r, rect_r)):
            i0, i1 = ev.window(t_ref - window_us, t_ref)
            xr, yr, t = rectify_window(ev, rect, i0, i1)
            imgs.append(make_image(args.repr, xr, yr, t, t_ref, calib.width, calib.height, tau_us))
            counts.append(event_count(xr, yr, calib.width, calib.height))
        res = match(imgs[0], imgs[1], counts[0], params, sign)
        disp = res["disparity"]
        depth = calib.depth_from_disparity(disp)
        ok = np.isfinite(depth)

        stats["support"] += int(res["support"].sum())
        stats["score"] += int(res["rejected_score"].sum())
        stats["unique"] += int(res["rejected_unique"].sum())
        stats["lr"] += int(res["rejected_lr"].sum())
        stats["kept"] += int(ok.sum())

        ys, xs = np.nonzero(ok)
        rows["frame"].append(np.full(xs.size, k, np.int32))
        rows["x"].append(xs.astype(np.int16))
        rows["y"].append(ys.astype(np.int16))
        rows["disparity"].append(disp[ok])
        rows["depth_m"].append(depth[ok].astype(np.float32))
        rows["score"].append(res["score"][ok])
        rows["margin"].append(res["margin"][ok])

        if args.roi:
            x0, y0, x1, y1 = args.roi
            z = depth[y0:y1, x0:x1]
            z = z[np.isfinite(z)]
            med = float(np.median(z)) if z.size else float("nan")
            roi_log.append((t_ref, med, z.size))
            print(f"  t = {(t_ref - t0) / 1e6:7.3f} s   roi median depth "
                  f"{med:6.3f} m from {z.size:4d} px")

        if args.preview:
            if zrange is None and ok.sum() > 50:
                zrange = tuple(np.percentile(depth[ok], [2, 98]))
            zr = zrange or (0.5, 10.0)
            preview(os.path.join(out_dir, "preview", f"{k:05d}.png"), imgs[0], imgs[1], depth,
                    zr[0], max(zr[1], zr[0] + 0.1), (t_ref - t0) / 1e6, int(ok.sum()))

    elapsed = time.time() - tic
    data = {key: np.concatenate(v) if v else np.zeros(0) for key, v in rows.items()}
    np.savez_compressed(os.path.join(out_dir, "depth.npz"), times_us=times, **data,
                        width=calib.width, height=calib.height, focal_px=calib.focal_px,
                        baseline_mm=calib.baseline_mm, repr=args.repr, window_ms=args.window_ms,
                        tau_ms=tau_us / 1000, patch=params.patch)
    if roi_log:
        np.savetxt(os.path.join(out_dir, "roi_depth.csv"), np.array(roi_log), delimiter=",",
                   header="t_us,median_depth_m,n_px", comments="", fmt=["%d", "%.4f", "%d"])

    s = stats
    print(f"\n{len(times)} steps in {elapsed:.1f} s ({elapsed / max(len(times), 1) * 1000:.0f} ms per step)")
    print(f"Pixels with enough events: {s['support']}")
    if s["support"]:
        print(f"  rejected, low score   : {s['score'] / s['support']:6.1%}")
        print(f"  rejected, not unique  : {s['unique'] / s['support']:6.1%}")
        print(f"  rejected, left-right  : {s['lr'] / s['support']:6.1%}")
        print(f"  kept                  : {s['kept'] / s['support']:6.1%}")
    if s["kept"]:
        z = data["depth_m"]
        print(f"Depth of kept pixels: median {np.median(z):.2f} m, 5-95% {np.percentile(z, 5):.2f} "
              f"to {np.percentile(z, 95):.2f} m")
    print(f"Results in {out_dir}")


if __name__ == "__main__":
    main()
