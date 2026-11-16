#!/usr/bin/env python3
"""Run depth.py with every representation on a simulated scene and compare.

    python tests/simulate_scene.py sessions/sim_depth
    python tests/compare_representations.py sessions/sim_depth [--repr count voxel] [extra depth.py options]
    python tests/compare_representations.py sessions/sim_depth --tag zncc --cost zncc

Each representation's output goes to <session>_depth_<repr>[_<tag>]/. Prints one
row per representation: how many points were kept, and their disparity errors
on the board and the wall. Options this script does not know are passed on
to depth.py.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from check_depth import evaluate  # noqa: E402
from evdepth.representation import REPRESENTATIONS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--repr", nargs="+", default=list(REPRESENTATIONS), choices=list(REPRESENTATIONS))
    ap.add_argument("--tag", default="", help="added to the output folder names, e.g. the matcher used")
    args, extra = ap.parse_known_args()      # everything else goes to depth.py
    session = args.session.rstrip("/")
    depth_py = os.path.join(HERE, "..", "depth.py")

    rows = []
    for name in args.repr:
        out = f"{session}_depth_{name}" + (f"_{args.tag}" if args.tag else "")
        print(f"Running {name} ...", flush=True)
        cmd = [sys.executable, depth_py, session, "--config", os.path.join(session, "config"),
               "--start-s", "0.05", "--step-ms", "25", "--repr", name, "--out", out, *extra]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        rows.append((name, evaluate(session, out)))

    print(f"\n{'repr':10s} {'points/step':>11s} | {'board MAE':>9s} {'>1 px':>6s} | "
          f"{'wall MAE':>8s} {'>1 px':>6s} | result")
    for name, r in rows:
        b, w = r["board"], r["wall"]
        print(f"{name:10s} {r['n_points'] / max(r['n_steps'], 1):11.0f} | {b['mae']:7.3f}px {b['outliers']:6.1%} | "
              f"{w['mae']:6.3f}px {w['outliers']:6.1%} | {'PASS' if r['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
