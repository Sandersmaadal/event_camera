#!/usr/bin/env python3
"""Compare depth methods on the lab recordings with a ball at a known distance.

    python tests/evaluate_lab.py --data ~/Documents/Project/data_collection/lab \\
        --config ~/Documents/Project/data_collection/sessions/lab_kalibrering/config --out results/lab
    python tests/evaluate_lab.py ... --methods voxel_census events

Every method in METHODS is run on every test in TESTS (depth.py or
depth_events.py, only in the time ranges where the ball is in view). Only
the points inside the ball's box count. For each test and method:

- points        matched pixels in the box, summed over all steps
- steps         steps with at least one point, of all steps
- median_m      median depth of the points
- error_pct     (median - truth) / truth
- mae_pct       mean |depth - truth| / truth
- within5/10    share of the points within ±5 % / ±10 % of the truth
- compute_x     computing time per second of recording (below 1 = faster
                than real time)
- rs_m          RealSense distance to the ball's centre (realsense_ball.py), median
                over the steps with points
- rs_error_pct, rs_mae_pct, rs_within10
                as above, but each point compared with the RealSense distance at the
                same moment (nearest ok RealSense frame within 70 ms) instead of the tape

Writes results.csv (one row per test and method) and summary.md (tables per
method) to --out. Runs that are already in --out are reused; delete the
folder or pass --rerun to compute again.

The ball boxes and times were found by eye from the event activity above the
background (rectified left image). Everything else that moves inside a box
also counts, so a few points may not be the ball.
"""
import argparse
import csv
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

# Ball tests: true distance, ball box (x0, y0, x1, y1) and time ranges (s from the start).
TESTS = {
    "lab_test01": dict(truth_m=1.0, roi=(0, 195, 300, 232), times=[(3.25, 4.05), (5.25, 6.55)]),
    "lab_test02": dict(truth_m=2.0, roi=(115, 155, 300, 190), times=[(4.2, 5.0)]),
    "lab_test03": dict(truth_m=3.0, roi=(100, 148, 215, 170), times=[(2.55, 3.45)]),
}

# name: (script, options). --row-shift from the command line comes first, so a
# method can override it.
METHODS = {
    "count_zncc": ("depth.py", ["--repr", "count", "--cost", "zncc"]),
    "count_census": ("depth.py", ["--repr", "count", "--cost", "census"]),
    "voxel_zncc": ("depth.py", ["--repr", "voxel", "--cost", "zncc"]),
    "voxel_census": ("depth.py", ["--repr", "voxel", "--cost", "census"]),
    "voxel_census_no_filter": ("depth.py", ["--repr", "voxel", "--cost", "census", "--noise-filter-ms", "0"]),
    "voxel_census_no_row_shift": ("depth.py", ["--repr", "voxel", "--cost", "census", "--row-shift", "0"]),
    "events": ("depth_events.py", []),
    "events_no_filter": ("depth_events.py", ["--noise-filter-ms", "0"]),
}
# The methods removed in the clean-up and their results: results/DECISIONS.md.

STEP_MS = 50.0
WINDOW_MS = 20.0        # depth.py / depth_events.py default; a step's time is the end of its window
RS_MAX_GAP_S = 0.07


def realsense_ball(test, args):
    """RealSense ball distance over time: (t_s, centre_m) arrays, computed once per test."""
    out = os.path.join(args.out, "realsense", test)
    path = os.path.join(out, "ball.csv")
    if args.rerun or not os.path.exists(path):
        cmd = [sys.executable, os.path.join(ROOT, "realsense_ball.py"), os.path.join(args.data, test),
               "--out", out, "--sheet"]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    rows = [r for r in csv.DictReader(open(path)) if r["ok"] == "1"]
    return np.array([float(r["t_s"]) for r in rows]), np.array([float(r["centre_m"]) for r in rows])


def run(method, test, rng, args):
    """Run one method on one time range; returns (output folder, computing time per second)."""
    script, options = METHODS[method]
    t_start, t_stop = rng
    out = os.path.join(args.out, "runs", f"{test}_{t_start:.2f}_{method}")
    log = os.path.join(out, "log.txt")
    if args.rerun or not os.path.exists(log):
        os.makedirs(out, exist_ok=True)
        cmd = [sys.executable, os.path.join(ROOT, script), os.path.join(args.data, test), "--config", args.config,
               "--start-s", str(t_start), "--duration-s", str(t_stop - t_start), "--step-ms", str(STEP_MS),
               "--max-disp", str(args.max_disp), "--row-shift", str(args.row_shift), *options, "--out", out]
        text = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        with open(log, "w") as f:
            f.write(" ".join(cmd) + "\n\n" + text)
    text = open(log).read()
    per_step = re.search(r"\((\d+) ms per step\)", text)          # depth.py
    per_second = re.search(r"([\d.]+) s of computing per second", text)   # depth_events.py
    compute = float(per_step.group(1)) / STEP_MS if per_step else float(per_second.group(1))
    return out, compute


def evaluate(test, method, args):
    spec = TESTS[test]
    x0, y0, x1, y1 = spec["roi"]
    z_all, rs_all, n_steps, steps_hit, computes = [], [], 0, 0, []
    rs_t, rs_z = realsense_ball(test, args) if args.realsense else (np.array([]), np.array([]))
    for rng in spec["times"]:
        out, compute = run(method, test, rng, args)
        computes.append(compute)
        d = np.load(os.path.join(out, "depth.npz"))
        inside = (d["x"] >= x0) & (d["x"] < x1) & (d["y"] >= y0) & (d["y"] < y1) & np.isfinite(d["depth_m"])
        z_all.append(d["depth_m"][inside])
        # RealSense distance at each point's step (middle of its window), NaN without a frame close by.
        t_mid = (d["times_us"][d["frame"][inside]] - WINDOW_MS * 500) / 1e6
        if rs_t.size:
            k = np.clip(np.searchsorted(rs_t, t_mid), 1, max(rs_t.size - 1, 1))
            k = np.where(np.abs(rs_t[k - 1] - t_mid) < np.abs(rs_t[k] - t_mid), k - 1, k)
            rs_all.append(np.where(np.abs(rs_t[k] - t_mid) <= RS_MAX_GAP_S, rs_z[k], np.nan))
        else:
            rs_all.append(np.full(t_mid.shape, np.nan))
        n_steps += len(d["times_us"])
        steps_hit += len(np.unique(d["frame"][inside]))
    z = np.concatenate(z_all)
    truth = spec["truth_m"]
    row = dict(test=test, truth_m=truth, method=method, points=z.size, steps=f"{steps_hit}/{n_steps}",
               compute_x=round(float(np.mean(computes)), 2))
    if z.size:
        rel = (z - truth) / truth
        med = float(np.median(z))
        row.update(median_m=round(med, 3), error_pct=round(100 * (med - truth) / truth, 1),
                   mae_pct=round(100 * float(np.mean(np.abs(rel))), 1),
                   within5=round(100 * float(np.mean(np.abs(rel) <= 0.05)), 1),
                   within10=round(100 * float(np.mean(np.abs(rel) <= 0.10)), 1))
        rs = np.concatenate(rs_all)
        ok = np.isfinite(rs)
        if ok.any():
            rel_rs = (z[ok] - rs[ok]) / rs[ok]
            row.update(rs_points=int(ok.sum()), rs_m=round(float(np.median(rs[ok])), 3),
                       rs_error_pct=round(100 * float(np.median(rel_rs)), 1),
                       rs_mae_pct=round(100 * float(np.mean(np.abs(rel_rs))), 1),
                       rs_within10=round(100 * float(np.mean(np.abs(rel_rs) <= 0.10)), 1))
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="folder with the lab_testNN recordings")
    ap.add_argument("--config", required=True, help="calibration folder")
    ap.add_argument("--out", required=True, help="folder for runs/, results.csv and summary.md")
    ap.add_argument("--methods", nargs="+", default=list(METHODS), choices=list(METHODS))
    ap.add_argument("--tests", nargs="+", default=list(TESTS), choices=list(TESTS))
    ap.add_argument("--row-shift", type=float, default=-2.0, help="see check_rectification.py")
    ap.add_argument("--max-disp", type=int, default=128, help="128 px reaches down to about 0.8 m")
    ap.add_argument("--rerun", action="store_true", help="compute runs again even if they exist")
    ap.add_argument("--no-realsense", dest="realsense", action="store_false",
                    help="skip the comparison with the RealSense ball distance")
    args = ap.parse_args()
    args.data = os.path.expanduser(args.data)
    args.config = os.path.expanduser(args.config)
    os.makedirs(args.out, exist_ok=True)

    rows = []
    for method in args.methods:
        for test in args.tests:
            print(f"{method:28s} {test} ...", flush=True)
            rows.append(evaluate(test, method, args))

    fields = ["test", "truth_m", "method", "points", "steps", "median_m", "error_pct", "mae_pct",
              "within5", "within10", "compute_x", "rs_points", "rs_m", "rs_error_pct", "rs_mae_pct",
              "rs_within10"]
    with open(os.path.join(args.out, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = [f"Row shift {args.row_shift:g} (unless the method sets its own), step {STEP_MS:g} ms.", ""]
    for test in args.tests:
        spec = TESTS[test]
        lines += [f"## {test}: ball at {spec['truth_m']:g} m", "",
                  "| Method | Points | Steps | Median | Error | MAE | Within ±5 % | Within ±10 % | Compute per s "
                  "| RealSense | Error vs RS | MAE vs RS | Within ±10 % of RS |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            if r["test"] == test:
                if r["points"]:
                    lines.append(f"| {r['method']} | {r['points']} | {r['steps']} | {r['median_m']:.3f} m | "
                                 f"{r['error_pct']:+.1f} % | {r['mae_pct']:.1f} % | {r['within5']:.0f} % | "
                                 f"{r['within10']:.0f} % | {r['compute_x']:.2f} s | " + (
                                     f"{r['rs_m']:.3f} m | {r['rs_error_pct']:+.1f} % | {r['rs_mae_pct']:.1f} % | "
                                     f"{r['rs_within10']:.0f} % |" if "rs_m" in r else "| | | |"))
                else:
                    lines.append(f"| {r['method']} | 0 | {r['steps']} | | | | | | {r['compute_x']:.2f} s | | | | |")
        lines.append("")
    summary = "\n".join(lines)
    with open(os.path.join(args.out, "summary.md"), "w") as f:
        f.write(summary)
    print("\n" + summary)


if __name__ == "__main__":
    main()
