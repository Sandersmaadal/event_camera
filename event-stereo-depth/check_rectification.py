#!/usr/bin/env python3
"""Measure how well the rows of a stereo recording line up after rectification.

    python check_rectification.py <recording> --config <config>
    python check_rectification.py <recording> --config <config> --start-s 4 --duration-s 2

After perfect rectification a point lies on the same row in both cameras.
This script matches every pixel with events not only on its own row but also
with the right image shifted up and down by up to --max-dy rows, and records
which row shift matches best (with a sub-pixel refinement). If the
calibration still fits the rig, the shifts are centred on 0 everywhere. A
constant offset means the cameras moved relative to each other after
calibration; an offset that changes across the image points to a calibration
error, typically near the image edges. An offset only on moving objects
points to a time offset between the cameras: test it with --right-offset-us.

dy > 0 means a point at row y in the left image is found at row y + dy in the
right image.

Only horizontal structure tells the row offset: a vertical edge looks the
same when shifted up or down. Pixels where the best shift does not clearly
win are therefore skipped (--min-margin).

Prints the median shift overall and in a grid over the image, and writes
rectification_check.png (histogram and map) to --out.
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "event-stereo-calib"))
from evcalib.events import load_events  # noqa: E402

from depth import find_inputs, rectify_window  # noqa: E402
from evdepth.costs import COSTS  # noqa: E402
from evdepth.matching import MatchParams  # noqa: E402
from evdepth.rectify import StereoCalib, make_rectifiers  # noqa: E402
from evdepth.representation import REPRESENTATIONS, ReprParams, event_count, make_representation  # noqa: E402


def shift_rows(rep, dy):
    """out[:, y] = rep[:, y + dy], zero where that is outside the image."""
    out = np.zeros_like(rep)
    H = rep.shape[1]
    if dy >= 0:
        out[:, :H - dy] = rep[:, dy:]
    else:
        out[:, -dy:] = rep[:, :H + dy]
    return out


def best_row_shift(rep_l, rep_r, count_l, params, sign, max_dy, min_margin):
    """Per pixel with events: the row shift with the lowest matching cost, NaN if unclear."""
    shifts = np.arange(-max_dy, max_dy + 1)
    # For every row shift, the cost of the best disparity at each pixel.
    best = np.stack([COSTS[params.cost](rep_l, shift_rows(rep_r, int(dy)), params, sign)[0].min(axis=2)
                     for dy in shifts])                                   # (shifts, H, W)
    i = np.argmin(best, axis=0)
    c = np.take_along_axis(best, i[None], 0)[0]
    # The best shift must beat the shifts further than one row away by a margin.
    far = np.abs(np.arange(shifts.size)[:, None, None] - i[None]) > 1
    margin = np.where(far, best, np.inf).min(axis=0) - c
    # Sub-pixel: parabola through the neighbouring shifts.
    ic = np.clip(i, 1, shifts.size - 2)
    c0, c1, c2 = (np.take_along_axis(best, (ic + o)[None], 0)[0] for o in (-1, 0, 1))
    denom = c0 - 2 * c1 + c2
    with np.errstate(divide="ignore", invalid="ignore"):
        off = np.clip(np.where(np.abs(denom) > 1e-6, 0.5 * (c0 - c2) / denom, 0.0), -0.5, 0.5)
    dy = shifts[ic] + off
    clear = ((count_l > 0) & (c <= params.max_cost) & (margin >= min_margin)
             & (i > 0) & (i < shifts.size - 1))                 # not at the edge of the search
    return np.where(clear, dy, np.nan)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="folder with left/right files, or a record_all prefix")
    ap.add_argument("--config", required=True, help="calibration folder")
    ap.add_argument("--out", help="folder for rectification_check.png (default: <recording>_rectification)")
    ap.add_argument("--repr", choices=list(REPRESENTATIONS), default="count")
    ap.add_argument("--cost", choices=list(COSTS), default="census")
    ap.add_argument("--max-dy", type=int, default=4, help="row shifts tried: -max-dy .. +max-dy")
    ap.add_argument("--min-margin", type=float, default=0.02, help="how clearly the best shift must win")
    ap.add_argument("--window-ms", type=float, default=20.0)
    ap.add_argument("--step-ms", type=float, default=200.0, help="time between the windows used")
    ap.add_argument("--start-s", type=float, default=0.0)
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--max-disp", type=int, default=MatchParams.max_disp)
    ap.add_argument("--right-offset-us", type=int, default=0,
                    help="added to right timestamps, to test a time offset between the cameras")
    ap.add_argument("--grid", type=int, default=4, help="the map shows grid x grid cells")
    args = ap.parse_args()

    params = MatchParams(cost=args.cost, max_disp=args.max_disp)
    calib = StereoCalib(args.config)
    rect_l, rect_r = make_rectifiers(calib)
    ev_l, ev_r = (load_events(f) for f in find_inputs(args.recording.rstrip("/")))
    if args.right_offset_us:
        ev_r.t = ev_r.t + args.right_offset_us
    window_us = int(args.window_ms * 1000)
    t0 = max(ev_l.t[0], ev_r.t[0]) + int(args.start_s * 1e6)
    t_end = min(ev_l.t[-1], ev_r.t[-1])
    if args.duration_s:
        t_end = min(t_end, t0 + int(args.duration_s * 1e6))
    times = np.arange(t0 + window_us, t_end + 1, int(args.step_ms * 1000))
    rparams = ReprParams()
    print(f"{len(times)} windows, repr '{args.repr}', cost '{args.cost}', row shifts "
          f"-{args.max_dy}..{args.max_dy}")

    xs, ys, dys = [], [], []
    for k, t in enumerate(times):
        win_l = rectify_window(ev_l, rect_l, t - window_us, t)
        win_r = rectify_window(ev_r, rect_r, t - window_us, t)
        rep_l = make_representation(args.repr, win_l, rparams)
        rep_r = make_representation(args.repr, win_r, rparams)
        dy = best_row_shift(rep_l, rep_r, event_count(win_l), params, calib.disparity_sign,
                            args.max_dy, args.min_margin)
        y, x = np.nonzero(np.isfinite(dy))
        xs.append(x), ys.append(y), dys.append(dy[y, x])
        print(f"  window {k + 1}/{len(times)}: {x.size} pixels, median shift "
              f"{np.median(dy[y, x]) if x.size else float('nan'):+.2f} rows", flush=True)
    x, y, dy = np.concatenate(xs), np.concatenate(ys), np.concatenate(dys)
    if dy.size == 0:
        sys.exit("No pixel gave a clear row shift. Try a part of the recording with more motion.")

    q25, med, q75 = np.percentile(dy, [25, 50, 75])
    print(f"\nRow shift over {dy.size} pixels: median {med:+.2f} rows (25-75 %: {q25:+.2f} to {q75:+.2f}), "
          f"{np.mean(np.abs(dy) <= 0.5):.0%} within ±0.5 rows")

    g, W, H = args.grid, calib.width, calib.height
    cell_med = np.full((g, g), np.nan)
    cell_n = np.zeros((g, g), int)
    print(f"\nMedian shift per cell ({g} x {g}, rows top to bottom; number of pixels in brackets):")
    for r in range(g):
        line = []
        for c in range(g):
            sel = (y * g // H == r) & (x * g // W == c)
            cell_n[r, c] = sel.sum()
            if cell_n[r, c] >= 50:
                cell_med[r, c] = np.median(dy[sel])
                line.append(f"{cell_med[r, c]:+5.2f} ({cell_n[r, c]:5d})")
            else:
                line.append(f"  --- ({cell_n[r, c]:5d})")
        print("  " + "  ".join(line))

    out_dir = args.out or (args.recording.rstrip("/") + "_rectification")
    os.makedirs(out_dir, exist_ok=True)
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    a.hist(dy, bins=np.arange(-args.max_dy, args.max_dy + 0.01, 0.25), color="0.4")
    a.axvline(0, color="k", lw=0.8)
    a.axvline(med, color="tab:red", lw=1.5, label=f"median {med:+.2f}")
    a.set_xlabel("row shift dy (rows)")
    a.set_ylabel("pixels")
    a.legend()
    lim = max(1.0, np.nanmax(np.abs(cell_med)) if np.isfinite(cell_med).any() else 1.0)
    im = b.imshow(cell_med, cmap="RdBu_r", vmin=-lim, vmax=lim, extent=(0, W, H, 0))
    for r in range(g):
        for c in range(g):
            if np.isfinite(cell_med[r, c]):
                b.text((c + 0.5) * W / g, (r + 0.5) * H / g, f"{cell_med[r, c]:+.2f}", ha="center",
                       va="center", fontsize=9)
    b.set_title("median row shift per cell (rectified left image)")
    fig.colorbar(im, ax=b, label="rows")
    path = os.path.join(out_dir, "rectification_check.png")
    fig.savefig(path, dpi=150)
    print(f"\nFigure: {path}")


if __name__ == "__main__":
    main()
