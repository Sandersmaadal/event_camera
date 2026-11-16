#!/usr/bin/env python3
"""Write the depth.npz from depth.py as CSV files.

    python depth_to_csv.py <recording>_depth
    python depth_to_csv.py <recording>_depth_voxel --roi 115 155 300 190

Writes next to depth.npz:

- points.csv    one row per matched pixel: frame, t_us, t_s, x, y,
                disparity_px, depth_m, cost, margin. x, y are in the rectified
                left image.
- per_step.csv  one row per step: frame, t_us, t_s, n_points, median_depth_m,
                q25_depth_m, q75_depth_m (empty when a step has no points).

t_us is the camera timestamp at the end of the step's window, t_s is seconds
since the first step. cost is how different the matched patches are (0 =
identical, 1 = no match) and margin how much better the match was than the
next-best disparity. Files from before costs were added have score (the ZNCC,
1 = perfect) in place of cost.

With --roi x0 y0 x1 y1 only the points inside that box are used, and the files
are called points_roi.csv and per_step_roi.csv.
"""
import argparse
import csv
import os

import numpy as np


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("depth_dir", help="output folder of depth.py (holds depth.npz)")
    ap.add_argument("--roi", type=int, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                    help="only points inside this box of the rectified left image")
    args = ap.parse_args()

    d = np.load(os.path.join(args.depth_dir, "depth.npz"))
    times = d["times_us"]
    keep = np.ones(d["x"].size, bool)
    suffix = ""
    if args.roi:
        x0, y0, x1, y1 = args.roi
        keep = (d["x"] >= x0) & (d["x"] < x1) & (d["y"] >= y0) & (d["y"] < y1)
        suffix = "_roi"
    frame, x, y = d["frame"][keep], d["x"][keep], d["y"][keep]
    disp, z = d["disparity"][keep], d["depth_m"][keep]
    quality = "cost" if "cost" in d.files else "score"
    score, margin = d[quality][keep], d["margin"][keep]
    t_s = (times - times[0]) / 1e6

    points_path = os.path.join(args.depth_dir, f"points{suffix}.csv")
    with open(points_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t_us", "t_s", "x", "y", "disparity_px", "depth_m", quality, "margin"])
        for k, xi, yi, di, zi, s, m in zip(frame, x, y, disp, z, score, margin):
            w.writerow([k, times[k], f"{t_s[k]:.3f}", xi, yi, f"{di:.3f}", f"{zi:.4f}", f"{s:.3f}", f"{m:.3f}"])

    step_path = os.path.join(args.depth_dir, f"per_step{suffix}.csv")
    with open(step_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "t_us", "t_s", "n_points", "median_depth_m", "q25_depth_m", "q75_depth_m"])
        for k, t in enumerate(times):
            zk = z[frame == k]
            if zk.size:
                q25, med, q75 = np.percentile(zk, [25, 50, 75])
                w.writerow([k, t, f"{t_s[k]:.3f}", zk.size, f"{med:.4f}", f"{q25:.4f}", f"{q75:.4f}"])
            else:
                w.writerow([k, t, f"{t_s[k]:.3f}", 0, "", "", ""])

    print(f"{z.size} points in {len(times)} steps -> {points_path}, {step_path}")


if __name__ == "__main__":
    main()
