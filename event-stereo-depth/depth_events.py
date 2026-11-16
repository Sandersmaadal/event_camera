#!/usr/bin/env python3
"""Event-by-event stereo depth with the C++ matcher (cpp/event_match.cpp).

    cpp/build.sh                                    # once, and after changing the C++ code
    python depth_events.py <recording> --config <config> --start-s 4.2 --duration-s 0.8 --row-shift -2

Unlike depth.py there are no time windows to match. The left and right events
are processed together in time order; every left event is matched the moment
it arrives, against the latest events of the right camera, and gets its own
disparity. For each left event:

- the recent left events in the --patch x --patch neighbourhood (at most
  --max-age-ms old) are collected,
- at every disparity, each of them is compared with the latest right event
  of the same polarity at the matching pixel (rows within --time-rows above
  and below too): cost min(time difference / --max-dt-ms, 1),
- the disparity with the lowest mean cost wins if it is below --max-cost and
  beats the disparities further than one pixel away by --min-margin,
- left-right check: the right camera's patch at the matched position is
  matched back to the left, and must land within --lr-tol pixels
  (--lr-tol -1 switches it off),
- sub-pixel disparity: a parabola through the costs around the best one.

The work is spread over --threads cores; the result does not depend on it.

Writes to --out (default <recording>_depth_events):

- events.npz  every left event: t_us, x, y, disparity, depth_m, cost, margin,
              status (0 too few events, 1 high cost, 2 not unique, 3 left-right
              check failed, 4 matched).
- depth.npz   the same format as depth.py, for depth_to_csv.py and comparing:
              steps every --step-ms, each with the matched events of the last
              --window-ms, the latest one per pixel.
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "event-stereo-calib"))
from evcalib.events import load_events  # noqa: E402

from depth import find_inputs, rectify_window  # noqa: E402
from evdepth.rectify import StereoCalib, make_rectifiers  # noqa: E402

try:
    from evdepth import _evmatch  # noqa: E402  (the C++ part, built with cpp/build.sh)
except ImportError:
    _evmatch = None

STATUS = ("too few recent events", "high cost", "not unique", "left-right check failed", "matched")


def whole_pixels(win):
    """Nearest whole-pixel position of every event."""
    x = np.clip(np.rint(win.x).astype(np.int64), 0, win.width - 1)
    y = np.clip(np.rint(win.y).astype(np.int64), 0, win.height - 1)
    return x, y


def to_steps(t, x, y, disp, depth, cost, margin, times, window_us):
    """Rows for depth.npz: per step the matched events of its window, the latest one per pixel."""
    rows = {key: [] for key in ("frame", "x", "y", "disparity", "depth_m", "cost", "margin")}
    matched = np.isfinite(depth)             # also leaves out disparity 0 (infinitely far), as depth.py does
    for k, t_ref in enumerate(times):
        sel = np.nonzero(matched & (t > t_ref - window_us) & (t <= t_ref))[0]
        pixel = y[sel] * 100_000 + x[sel]
        # np.unique keeps the first index per pixel; reversed, that is the latest event.
        _, first = np.unique(pixel[::-1], return_index=True)
        sel = sel[::-1][first]
        rows["frame"].append(np.full(sel.size, k, np.int32))
        rows["x"].append(x[sel].astype(np.int16))
        rows["y"].append(y[sel].astype(np.int16))
        rows["disparity"].append(disp[sel])
        rows["depth_m"].append(depth[sel].astype(np.float32))
        rows["cost"].append(cost[sel])
        rows["margin"].append(margin[sel])
    return {key: np.concatenate(v) for key, v in rows.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="folder with left/right files, or a record_all prefix")
    ap.add_argument("--config", required=True, help="calibration folder")
    ap.add_argument("--out", help="output folder (default: <recording>_depth_events)")
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--row-shift", type=float, default=0.0, help="as in depth.py")
    ap.add_argument("--min-disp", type=int, default=0)
    ap.add_argument("--max-disp", type=int, default=96)
    ap.add_argument("--patch", type=int, default=11)
    ap.add_argument("--max-dt-ms", type=float, default=5.0, help="time difference that counts as no match")
    ap.add_argument("--max-age-ms", type=float, default=20.0, help="left events older than this are ignored")
    ap.add_argument("--time-rows", type=int, default=2, help="rows above and below searched in the other camera")
    ap.add_argument("--min-events", type=int, default=6, help="recent left events in the patch needed")
    ap.add_argument("--max-cost", type=float, default=0.6)
    ap.add_argument("--min-margin", type=float, default=0.02)
    ap.add_argument("--lr-tol", type=float, default=1.0, help="left-right check tolerance, pixels; -1 = off")
    ap.add_argument("--threads", type=int, default=0, help="cores to use, 0 = all")
    ap.add_argument("--step-ms", type=float, default=50.0, help="steps of depth.npz")
    ap.add_argument("--window-ms", type=float, default=20.0, help="events per step in depth.npz")
    args = ap.parse_args()
    if _evmatch is None:
        sys.exit("The C++ module is not built. Run cpp/build.sh (needs cmake and pip install pybind11).")

    calib = StereoCalib(args.config)
    rect_l, rect_r = make_rectifiers(calib)
    ev_l, ev_r = (load_events(f) for f in find_inputs(args.recording.rstrip("/")))
    t0 = max(ev_l.t[0], ev_r.t[0]) + int(args.start_s * 1e6)
    t_end = min(ev_l.t[-1], ev_r.t[-1])
    if args.duration_s:
        t_end = min(t_end, t0 + int(args.duration_s * 1e6))
    win_l = rectify_window(ev_l, rect_l, t0, t_end)
    win_r = rectify_window(ev_r, rect_r, t0, t_end, args.row_shift)
    xl, yl = whole_pixels(win_l)
    xr, yr = whole_pixels(win_r)
    print(f"{xl.size} left and {xr.size} right events in {(t_end - t0) / 1e6:.2f} s")

    tic = time.time()
    res = _evmatch.match_events(xl, yl, win_l.on, win_l.t, xr, yr, win_r.on, win_r.t,
                                calib.width, calib.height, args.min_disp, args.max_disp,
                                int(calib.disparity_sign), args.patch, args.max_dt_ms * 1000,
                                args.max_age_ms * 1000, args.time_rows, args.min_events,
                                args.max_cost, args.min_margin, args.lr_tol, args.threads)
    elapsed = time.time() - tic
    disp = res["disparity"]
    depth = calib.depth_from_disparity(disp).astype(np.float32)
    matched = np.isfinite(depth)             # also leaves out disparity 0 (infinitely far), as depth.py does
    print(f"Matched {matched.sum()} of {xl.size} left events ({matched.mean():.1%}) in {elapsed:.2f} s: "
          f"{elapsed / max(xl.size, 1) * 1e6:.1f} us per event, "
          f"{elapsed / ((t_end - t0) / 1e6):.2f} s of computing per second of recording")
    counts = np.bincount(res["status"], minlength=len(STATUS))
    print("  " + ", ".join(f"{name} {c / max(xl.size, 1):.1%}" for name, c in zip(STATUS, counts)))
    if matched.any():
        z = depth[matched]
        print(f"Depth of matched events: median {np.median(z):.2f} m, 5-95% "
              f"{np.percentile(z, 5):.2f} to {np.percentile(z, 95):.2f} m")

    out_dir = args.out or (args.recording.rstrip("/") + "_depth_events")
    os.makedirs(out_dir, exist_ok=True)
    np.savez_compressed(os.path.join(out_dir, "events.npz"), t_us=win_l.t, x=xl.astype(np.int16),
                        y=yl.astype(np.int16), disparity=disp, depth_m=depth, cost=res["cost"],
                        margin=res["margin"], status=res["status"])
    window_us = int(args.window_ms * 1000)
    times = np.arange(t0 + window_us, t_end + 1, int(args.step_ms * 1000))
    data = to_steps(win_l.t, xl, yl, disp, depth, res["cost"], res["margin"], times, window_us)
    np.savez_compressed(os.path.join(out_dir, "depth.npz"), times_us=times, **data,
                        width=calib.width, height=calib.height, focal_px=calib.focal_px,
                        baseline_mm=calib.baseline_mm, repr="events", window_ms=args.window_ms,
                        patch=args.patch, cost_name="events_cpp", max_dt_ms=args.max_dt_ms,
                        lr_tol=args.lr_tol)
    print(f"Results in {out_dir}")


if __name__ == "__main__":
    main()
