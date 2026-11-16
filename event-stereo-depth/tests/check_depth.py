#!/usr/bin/env python3
"""Compare depth.py's output on a simulated scene with the true depth.

    python tests/check_depth.py sessions/sim_depth [--depth-dir sessions/sim_depth_depth]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from evdepth.rectify import StereoCalib  # noqa: E402


def true_depth_rectified(calib, truth):
    """True depth (rectified left frame, metres) for every rectified left pixel, and the surface."""
    xs, ys = np.meshgrid(np.arange(calib.width, dtype=float), np.arange(calib.height, dtype=float))
    pix = np.stack([xs.ravel(), ys.ravel(), np.ones(xs.size)], 1)
    d_rect = pix @ np.linalg.inv(calib.P1[:, :3]).T
    d_left = d_rect @ calib.R1                 # R1^T applied to each row vector
    s_near = truth["near_mm"] / d_left[:, 2]
    p = s_near[:, None] * d_left
    on_board = (np.abs(p[:, 0]) < truth["board_half_mm"]) & (np.abs(p[:, 1]) < truth["board_half_mm"])
    s = np.where(on_board, s_near, truth["far_mm"] / d_left[:, 2])
    X_rect = (s[:, None] * d_left) @ calib.R1.T
    z = (X_rect[:, 2] / 1000.0).reshape(calib.height, calib.width)
    return z, on_board.reshape(calib.height, calib.width)


def evaluate(session, depth_dir):
    """Error statistics of depth.py's output against the true depth.

    Returns {"n_steps", "n_points", "board": {...}, "wall": {...}, "outliers", "pass"}.
    """
    calib = StereoCalib(os.path.join(session, "config"))
    with open(os.path.join(session, "truth.json")) as f:
        truth = json.load(f)
    d = np.load(os.path.join(depth_dir, "depth.npz"))
    z_true, on_board = true_depth_rectified(calib, truth)
    x, y, z = d["x"].astype(int), d["y"].astype(int), d["depth_m"]
    zt, board = z_true[y, x], on_board[y, x]
    disp_true = calib.focal_px * calib.baseline_mm / (zt * 1000)
    disp_err = d["disparity"] - disp_true
    rel = np.abs(z - zt) / zt

    out = {"n_steps": int(d["times_us"].size), "n_points": int(z.size)}
    for name, m in (("board", board), ("wall", ~board)):
        e = disp_err[m]
        out[name] = {"n": int(m.sum()), "z_true": float(zt[m].mean()) if m.any() else float("nan"),
                     "z_median": float(np.median(z[m])) if m.any() else float("nan"),
                     "err_median": float(np.median(e)) if m.any() else float("nan"),
                     "mae": float(np.mean(np.abs(e))) if m.any() else float("nan"),
                     "outliers": float(np.mean(np.abs(e) > 1)) if m.any() else float("nan"),
                     "rel_median": float(np.median(rel[m])) if m.any() else float("nan")}
    out["outliers"] = float(np.mean(np.abs(disp_err) > 1)) if z.size else 1.0
    out["pass"] = bool(z.size and out["outliers"] < 0.05 and np.median(np.abs(disp_err)) < 0.5)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session")
    ap.add_argument("--depth-dir")
    args = ap.parse_args()
    session = args.session.rstrip("/")
    r = evaluate(session, args.depth_dir or session + "_depth")

    print(f"{r['n_points']} depth points over {r['n_steps']} steps, "
          f"{r['n_points'] / max(r['n_steps'], 1):.0f} per step")
    for name in ("board", "wall"):
        s = r[name]
        if not s["n"]:
            continue
        print(f"{name:5s} true {s['z_true']:.2f} m: {s['n']:6d} pts, median depth {s['z_median']:.3f} m, "
              f"disparity error median {s['err_median']:+.3f} px, MAE {s['mae']:.3f} px, "
              f"outliers (>1 px) {s['outliers']:.1%}, rel. depth error median {s['rel_median']:.1%}")
    print("PASS" if r["pass"] else "FAIL")
    sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
