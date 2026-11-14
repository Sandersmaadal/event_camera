#!/usr/bin/env python3
"""Simulate a stereo event recording of a scene with known depth.

    python tests/simulate_scene.py sessions/sim_depth
    python depth.py sessions/sim_depth --config sessions/sim_depth/config --preview
    python tests/check_depth.py sessions/sim_depth

The scene is a textured board in front of a textured wall, both parallel to
the rig. The texture slides sideways (like a passing boat in front of the
water), so the geometry stays fixed and every pixel's true depth is known.
The cameras have lens distortion and are slightly rotated relative to each
other, so rectification is exercised too.

Events are made the way an event camera makes them: each pixel fires when its
log brightness has changed by a contrast threshold since its last event, with
threshold noise, timestamp jitter and random noise events.
"""
import argparse
import json
import os

import cv2
import numpy as np

W = H = 320


def make_rig(baseline_mm):
    KL = np.array([[170.0, 0, 161.0], [0, 170.5, 158.0], [0, 0, 1]])
    KR = np.array([[171.5, 0, 158.5], [0, 171.0, 162.0], [0, 0, 1]])
    DL = np.array([[-0.12, 0.03, 0.0005, -0.0004, 0.0]])
    DR = np.array([[-0.10, 0.02, -0.0003, 0.0006, 0.0]])
    R = cv2.Rodrigues(np.radians(np.array([0.6, -1.2, 0.8])).reshape(3, 1))[0]
    # X_right = R X_left + T: the right camera sits baseline_mm to the right.
    T = np.array([[-baseline_mm], [1.5], [-2.0]])
    return KL, DL, KR, DR, R, T


def write_config(out, KL, DL, KR, DR, R, T):
    os.makedirs(out, exist_ok=True)
    for side, K, D in (("left", KL, DL), ("right", KR, DR)):
        with open(os.path.join(out, f"camera_{side}.json"), "w") as f:
            json.dump({"type": "pinhole", "width": W, "height": H, "K": K.tolist(), "D": D.tolist(),
                       "RMS": 0.0, "n_images_used": 0}, f, indent=4)
    with open(os.path.join(out, "stereo_params.json"), "w") as f:
        json.dump({"R": R.tolist(), "T": T.tolist(), "units": "mm",
                   "baseline_mm": float(np.linalg.norm(T))}, f, indent=4)


class Scene:
    """Board at z_near (limited size) in front of a wall at z_far. Units mm."""

    def __init__(self, z_near, z_far, board_half_mm, v_near, v_far, seed=0):
        rng = np.random.default_rng(seed)
        tex = rng.random((512, 512)).astype(np.float32)
        tex = cv2.GaussianBlur(tex, (0, 0), 2.5)
        tex = (tex - tex.min()) / (tex.max() - tex.min())
        self.tex = 0.15 + 0.85 * tex            # brightness, never zero
        self.z_near, self.z_far = z_near, z_far
        self.half = board_half_mm
        self.v_near, self.v_far = v_near, v_far  # texture speed, mm/s
        self.mm_per_px_near, self.mm_per_px_far = 20.0, 60.0   # features ~4 image px wide

    def hit(self, origin, dirs):
        """Depth along z of the first surface each ray hits, and which surface."""
        s_near = (self.z_near - origin[2]) / dirs[:, 2]
        p = origin + s_near[:, None] * dirs
        on_board = (np.abs(p[:, 0]) < self.half) & (np.abs(p[:, 1]) < self.half)
        s = np.where(on_board, s_near, (self.z_far - origin[2]) / dirs[:, 2])
        return origin + s[:, None] * dirs, on_board

    def brightness(self, pts, on_board, t_s):
        u = np.where(on_board, (pts[:, 0] - self.v_near * t_s) / self.mm_per_px_near,
                     (pts[:, 0] - self.v_far * t_s) / self.mm_per_px_far)
        v = np.where(on_board, pts[:, 1] / self.mm_per_px_near, pts[:, 1] / self.mm_per_px_far + 100)
        mx = np.mod(u, 512).astype(np.float32).reshape(H, W)
        my = np.mod(v, 512).astype(np.float32).reshape(H, W)
        return cv2.remap(self.tex, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def rays(K, D, R_to_left=None):
    xs, ys = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    n = cv2.undistortPoints(np.stack([xs.ravel(), ys.ravel()], 1).reshape(-1, 1, 2), K, D).reshape(-1, 2)
    d = np.column_stack([n, np.ones(len(n))])
    return d if R_to_left is None else d @ R_to_left.T


def simulate_camera(scene, origin, dirs, duration_s, dt_s, rng, contrast=0.18, noise_hz=0.5):
    pts, on_board = scene.hit(origin, dirs)
    ref = np.log(scene.brightness(pts, on_board, 0.0)).ravel()
    th = contrast * (1 + 0.1 * rng.standard_normal(ref.size))   # per-pixel threshold mismatch
    xs, ys, ps, ts = [], [], [], []
    for k in range(1, int(duration_s / dt_s) + 1):
        t = k * dt_s
        cur = np.log(scene.brightness(pts, on_board, t)).ravel()
        diff = cur - ref
        fire = np.abs(diff) >= th
        idx = np.nonzero(fire)[0]
        if idx.size:
            xs.append(idx % W)
            ys.append(idx // W)
            ps.append((diff[idx] > 0).astype(np.uint8))
            jitter = rng.uniform(-dt_s, 0, idx.size)
            ts.append(np.round((t + jitter) * 1e6).astype(np.int64))
            ref[idx] = cur[idx]
    # Background noise events.
    n_noise = rng.poisson(noise_hz * W * H * duration_s)
    xs.append(rng.integers(0, W, n_noise))
    ys.append(rng.integers(0, H, n_noise))
    ps.append(rng.integers(0, 2, n_noise).astype(np.uint8))
    ts.append(rng.integers(0, int(duration_s * 1e6), n_noise).astype(np.int64))
    x, y, p, t = (np.concatenate(a) for a in (xs, ys, ps, ts))
    order = np.argsort(t, kind="stable")
    return x[order].astype(np.uint16), y[order].astype(np.uint16), p[order], t[order]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--baseline-mm", type=float, default=400.0)
    ap.add_argument("--near-m", type=float, default=2.0)
    ap.add_argument("--far-m", type=float, default=6.0)
    ap.add_argument("--duration-s", type=float, default=0.5)
    args = ap.parse_args()

    rng = np.random.default_rng(1)
    KL, DL, KR, DR, R, T = make_rig(args.baseline_mm)
    write_config(os.path.join(args.out, "config"), KL, DL, KR, DR, R, T)
    scene = Scene(args.near_m * 1000, args.far_m * 1000, board_half_mm=0.35 * args.near_m * 1000,
                  v_near=3000.0, v_far=-4000.0)

    origin_l = np.zeros(3)
    origin_r = (-R.T @ T).ravel()            # right camera centre in the left frame
    dirs_l = rays(KL, DL)
    dirs_r = rays(KR, DR, R.T)               # right rays rotated into the left frame
    for side, origin, dirs in (("left", origin_l, dirs_l), ("right", origin_r, dirs_r)):
        x, y, p, t = simulate_camera(scene, origin, dirs, args.duration_s, 0.5e-3, rng)
        np.savez_compressed(os.path.join(args.out, f"{side}.npz"), x=x, y=y, p=p, t=t, width=W, height=H)
        print(f"{side}: {t.size} events ({t.size / args.duration_s / 1e6:.2f} Mev/s)")

    with open(os.path.join(args.out, "truth.json"), "w") as f:
        json.dump({"near_mm": scene.z_near, "far_mm": scene.z_far, "board_half_mm": scene.half,
                   "baseline_mm": args.baseline_mm}, f, indent=4)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
