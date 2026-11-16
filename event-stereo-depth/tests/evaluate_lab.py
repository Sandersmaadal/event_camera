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
    "voxel_census_no_row_shift": ("depth.py", ["--repr", "voxel", "--cost", "census", "--row-shift", "0"]),
    "events": ("depth_events.py", []),
}
# The methods removed in the clean-up and their results: results/DECISIONS.md.

STEP_MS = 50.0


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
    z_all, n_steps, steps_hit, computes = [], 0, 0, []
    for rng in spec["times"]:
        out, compute = run(method, test, rng, args)
        computes.append(compute)
        d = np.load(os.path.join(out, "depth.npz"))
        inside = (d["x"] >= x0) & (d["x"] < x1) & (d["y"] >= y0) & (d["y"] < y1) & np.isfinite(d["depth_m"])
        z_all.append(d["depth_m"][inside])
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
              "within5", "within10", "compute_x"]
    with open(os.path.join(args.out, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = [f"Row shift {args.row_shift:g} (unless the method sets its own), step {STEP_MS:g} ms.", ""]
    for test in args.tests:
        spec = TESTS[test]
        lines += [f"## {test}: ball at {spec['truth_m']:g} m", "",
                  "| Method | Points | Steps | Median | Error | MAE | Within ±5 % | Within ±10 % | Compute per s |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            if r["test"] == test:
                if r["points"]:
                    lines.append(f"| {r['method']} | {r['points']} | {r['steps']} | {r['median_m']:.3f} m | "
                                 f"{r['error_pct']:+.1f} % | {r['mae_pct']:.1f} % | {r['within5']:.0f} % | "
                                 f"{r['within10']:.0f} % | {r['compute_x']:.2f} s |")
                else:
                    lines.append(f"| {r['method']} | 0 | {r['steps']} | | | | | | {r['compute_x']:.2f} s |")
        lines.append("")
    summary = "\n".join(lines)
    with open(os.path.join(args.out, "summary.md"), "w") as f:
        f.write(summary)
    print("\n" + summary)


if __name__ == "__main__":
    main()
