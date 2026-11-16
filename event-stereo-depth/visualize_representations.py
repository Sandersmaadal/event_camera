#!/usr/bin/env python3
"""Figure of every event representation for one time window, for reports.

    python visualize_representations.py <recording> --config <config> --t-s 2.5
    python visualize_representations.py <recording> --config <config> --t-s 2.5 --roi 100 80 220 200

Takes the --window-ms of events ending at --t-s (seconds from the start of the
recording), rectifies them like depth.py does, and draws:

- the raw events as a space-time point cloud (red = ON, blue = OFF),
- every representation in evdepth/representation.py (the voxel grid as one
  panel per time bin).

The figure with all six representations that were compared (including the
removed time surfaces and polarity split) is saved in
results/figures/representations_lab_test02_4.2s.png.

Output in --out (default <recording>_repr_<t>s/):

- overview.png and overview.pdf: all panels in one figure,
- panels/<name>.png: each panel alone at native resolution (scaled up with
  nearest-neighbour), for building your own figure in LaTeX or similar.

--roi x0 y0 x1 y1 crops all panels to that box of the rectified image, to zoom
in on the object of the experiment.
"""
import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# depth.py also puts event-stereo-calib on the path, so evcalib imports after it.
from depth import find_inputs, rectify_window  # noqa: E402
from evcalib.events import load_events  # noqa: E402
from evdepth.rectify import StereoCalib, make_rectifiers  # noqa: E402
from evdepth.representation import REPRESENTATIONS, ReprParams, make_representation  # noqa: E402

ON_COLOR = np.array([0.85, 0.15, 0.10])    # red
OFF_COLOR = np.array([0.10, 0.30, 0.85])   # blue


def _scale(img, pct=99.0):
    """Divide by a high percentile of the non-zero values, clip to 0..1."""
    nz = np.abs(img[img != 0])
    m = np.percentile(nz, pct) if nz.size else 1.0
    return np.clip(img / max(m, 1e-9), -1, 1)


def gray(img):
    """White background, dark where there are many events."""
    v = 1 - _scale(img)
    return np.dstack([v, v, v])


def signed(img, vmax):
    """Diverging map for signed values: red positive (ON), blue negative (OFF), white zero."""
    return plt.get_cmap("RdBu_r")(np.clip(img / vmax, -1, 1) * 0.5 + 0.5)[..., :3]


def panels_for(name, rep, params):
    """[(file name, title, rgb image)] for one representation of shape (C, H, W)."""
    if name == "count":
        return [(name, "count\nevents per pixel", gray(rep[0]))]
    if name == "voxel":
        nz = np.abs(rep[rep != 0])
        vmax = np.percentile(nz, 99) if nz.size else 1.0
        return [(f"voxel_bin{b}", f"voxel bin {b + 1}/{rep.shape[0]}\nred = ON, blue = OFF", signed(rep[b], vmax))
                for b in range(rep.shape[0])]
    # A representation added later without its own colouring: one grey panel per channel.
    return [(f"{name}_c{c}", f"{name} channel {c}", gray(np.abs(rep[c]))) for c in range(rep.shape[0])]


def space_time(ax, win, roi, max_points=20000, seed=0):
    """3-D scatter of the events in the window, x and y against time."""
    keep = np.ones(win.t.size, bool)
    if roi:
        x0, y0, x1, y1 = roi
        keep = (win.x >= x0) & (win.x < x1) & (win.y >= y0) & (win.y < y1)
    idx = np.nonzero(keep)[0]
    if idx.size > max_points:
        idx = np.sort(np.random.default_rng(seed).choice(idx, max_points, replace=False))
    t_ms = (win.t[idx] - win.t_start) / 1000.0
    colors = np.where(win.on[idx, None], ON_COLOR, OFF_COLOR)
    ax.scatter(win.x[idx], t_ms, win.y[idx], c=colors, s=0.3, alpha=0.6, linewidths=0)
    ax.set_xlabel("x [px]")
    ax.set_ylabel("t [ms]")
    ax.set_zlabel("y [px]")
    ax.invert_zaxis()              # image y points down
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_major_locator(matplotlib.ticker.MaxNLocator(4))
    ax.set_title(f"events\n{idx.size} shown")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="folder with left/right files, or a record_all prefix")
    ap.add_argument("--config", required=True, help="calibration folder, as for depth.py")
    ap.add_argument("--t-s", type=float, required=True, help="end of the window, seconds from the start")
    ap.add_argument("--window-ms", type=float, default=20.0)
    ap.add_argument("--bins", type=int, default=ReprParams.bins)
    ap.add_argument("--camera", choices=("left", "right"), default="left")
    ap.add_argument("--repr", nargs="+", default=list(REPRESENTATIONS), choices=list(REPRESENTATIONS),
                    help="representations to draw, in this order")
    ap.add_argument("--roi", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                    help="crop to this box of the rectified image")
    ap.add_argument("--cols", type=int, default=None, help="panels per row in the overview (default: square grid)")
    ap.add_argument("--scale", type=int, default=3, help="upscaling of the single-panel PNGs")
    ap.add_argument("--out", help="output folder")
    args = ap.parse_args()

    window_us = args.window_ms * 1000
    params = ReprParams(bins=args.bins)

    calib = StereoCalib(args.config)
    rect = make_rectifiers(calib)[0 if args.camera == "left" else 1]
    left_file, right_file = find_inputs(args.recording.rstrip("/"))
    ev = load_events(left_file if args.camera == "left" else right_file)
    t_end = ev.t[0] + args.t_s * 1e6
    if t_end > ev.t[-1]:
        sys.exit(f"--t-s {args.t_s} is after the end of the recording "
                 f"({(ev.t[-1] - ev.t[0]) / 1e6:.2f} s).")
    win = rectify_window(ev, rect, t_end - window_us, t_end)
    print(f"{win.t.size} events in the {args.window_ms:g} ms window ending at {args.t_s:g} s")

    panels = []
    for name in args.repr:
        panels += panels_for(name, make_representation(name, win, params), params)
    if args.roi:
        x0, y0, x1, y1 = args.roi
        panels = [(f, title, rgb[y0:y1, x0:x1]) for f, title, rgb in panels]

    out = args.out or f"{args.recording.rstrip('/')}_repr_{args.t_s:g}s"
    os.makedirs(os.path.join(out, "panels"), exist_ok=True)
    for fname, _, rgb in panels:
        big = np.repeat(np.repeat(rgb, args.scale, 0), args.scale, 1)
        plt.imsave(os.path.join(out, "panels", f"{fname}.png"), big)

    n = len(panels) + 1                          # + the space-time plot
    cols = args.cols or int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    fig = plt.figure(figsize=(3.4 * cols, 3.6 * rows), layout="constrained")
    space_time(fig.add_subplot(rows, cols, 1, projection="3d"), win, args.roi)
    for i, (_, title, rgb) in enumerate(panels, start=2):
        ax = fig.add_subplot(rows, cols, i)
        ax.imshow(rgb, interpolation="nearest")
        ax.set_title(title, fontsize=9)
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(f"{args.camera} camera, rectified, {args.window_ms:g} ms window ending at t = {args.t_s:g} s",
                 fontsize=11)
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(out, f"overview.{ext}"), dpi=200)
    print(f"Wrote {out}/overview.png, overview.pdf and {len(panels)} panels in {out}/panels/")


if __name__ == "__main__":
    main()
