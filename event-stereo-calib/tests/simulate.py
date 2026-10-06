"""Simulate a stereo pair of event cameras looking at a flickering checkerboard.

This produces left.npz / right.npz in the same format as convert.py, plus the
ground-truth calibration, so the whole pipeline can be checked end to end
without any hardware:

    python tests/simulate.py sessions/sim
    python detect.py sessions/sim
    python calibrate.py sessions/sim --square-mm 70

The sensor model is a simple one: a pixel fires one event each time its log
intensity has changed by a contrast threshold. The rig moves from pose to
pose and holds still at each one, and the board keeps flipping throughout,
so the recording contains both clean flips and flips that happen in motion.
"""
import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evcalib.events import Events, save_npz  # noqa: E402

W = H = 320
GT = {
    "K_left": [[168.8, 0, 167.2], [0, 168.5, 162.3], [0, 0, 1]],
    "D_left": [0.063, -0.020, 0.0023, 0.0046, 0.0],
    "K_right": [[170.1, 0, 158.4], [0, 169.7, 165.0], [0, 0, 1]],
    "D_right": [0.055, -0.015, -0.0030, 0.0020, 0.0],
    "rvec": [0.02, -0.06, 0.015],          # left -> right rotation (Rodrigues)
    "T": [-95.0, 2.5, 4.0],                # mm
}
COLS, ROWS = 9, 6                          # inner corners


def subpixel_rays(K, D, ss):
    """Unit-depth rays for an ss x ss grid of sample points inside every pixel."""
    off = (np.arange(ss) + 0.5) / ss - 0.5
    xs = (np.arange(W)[:, None] + off[None, :]).ravel()
    ys = (np.arange(H)[:, None] + off[None, :]).ravel()
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel()], 1).astype(np.float64).reshape(-1, 1, 2)
    n = cv2.undistortPoints(pts, K, D).reshape(-1, 2)
    return np.concatenate([n, np.ones((n.shape[0], 1))], 1), ss


def render(rays_ss, R, t, state_b, sq):
    """Linear intensity image seen by a camera with pose X_cam = R X_board + t."""
    rays, ss = rays_ss
    o = -R.T @ t                                    # camera centre in the board frame
    d = rays @ R                                    # = (R.T @ rays.T).T
    s = -o[2] / d[:, 2]
    x = o[0] + s * d[:, 0]
    y = o[1] + s * d[:, 1]
    i = np.floor(x / sq).astype(np.int64) + 1       # square index, 0..9
    j = np.floor(y / sq).astype(np.int64) + 1       # square index, 0..6
    on_board = (i >= 0) & (i < COLS + 1) & (j >= 0) & (j < ROWS + 1) & (s > 0)
    white = ((i + j) % 2 == 0) ^ state_b
    # The TV around the board is dark; the wall behind it has some texture.
    on_tv = (x > -1.8 * sq) & (x < (COLS + 1.8) * sq) & (y > -1.3 * sq) & (y < (ROWS + 1.3) * sq)
    wall = 0.25 + 0.35 * (((np.floor(x / 130.0) * 7 + np.floor(y / 130.0) * 13) % 5) / 4.0)
    img = np.where(on_board, np.where(white, 1.0, 0.03), np.where(on_tv, 0.05, wall))
    img = np.where(s > 0, img, 0.3)
    return img.reshape(H, ss, W, ss).mean(axis=(1, 3))


def look_at_pose(rng, sq):
    """Random rig pose in front of the board, as (rvec, t) of the left camera."""
    bw, bh = (COLS - 1) * sq, (ROWS - 1) * sq
    centre = np.array([bw / 2, bh / 2, 0.0])
    dist = rng.uniform(650, 1250)
    az, el = np.deg2rad(rng.uniform(-30, 30)), np.deg2rad(rng.uniform(-22, 22))
    n = np.array([np.sin(az) * np.cos(el), np.sin(el), -np.cos(az) * np.cos(el)])
    cam = centre + rng.uniform(-0.15, 0.15, 3) * [bw, bh, 0] + dist * n
    # Aim somewhere near the board centre, so the board lands in different
    # parts of the image.
    aim_spread = 0.45 * dist
    target = centre + np.array([rng.uniform(-1, 1) * aim_spread, rng.uniform(-1, 1) * aim_spread * 0.7, 0])
    z = target - cam
    z /= np.linalg.norm(z)
    up = np.array([0.0, 1.0, 0.0])
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z])                          # rows = camera axes in board frame
    roll, _ = cv2.Rodrigues(np.array([0, 0, np.deg2rad(rng.uniform(-10, 10))]))
    R = roll @ R
    t = -R @ cam
    return cv2.Rodrigues(R)[0].ravel(), t


def project(K, D, R, t, sq):
    obj = np.zeros((ROWS * COLS, 3))
    obj[:, :2] = np.mgrid[0:COLS, 0:ROWS].T.reshape(-1, 2) * sq
    p, _ = cv2.projectPoints(obj, cv2.Rodrigues(R)[0], t, K, D)
    return p.reshape(-1, 2)


def board_visible(K, D, R, t, sq, margin=6):
    p = project(K, D, R, t, sq)
    # also keep the outer squares in view
    return bool(np.all((p > margin) & (p < W - margin)))


class Sensor:
    """Per-pixel contrast-threshold event generator."""

    def __init__(self, rng, c=1.0):
        self.rng = rng
        self.c = c * (1 + 0.12 * rng.standard_normal((H, W))).clip(0.6, 1.5)
        self.ref = None
        self.out = []

    def step(self, img, t_prev, t_now, flip_scan=None):
        logi = np.log(img + 1e-3)
        if self.ref is None:
            self.ref = logi.copy()
            return
        diff = logi - self.ref
        n = np.floor(np.abs(diff) / self.c).astype(np.int64)
        n = np.minimum(n, 4)
        ys, xs = np.nonzero(n)
        if ys.size == 0:
            return
        cnt = n[ys, xs]
        sign = diff[ys, xs] > 0
        self.ref[ys, xs] += np.where(sign, 1, -1) * cnt * self.c[ys, xs]
        # A pixel that reached its cap keeps no memory of the remaining change.
        capped = cnt == 4
        self.ref[ys[capped], xs[capped]] = logi[ys[capped], xs[capped]]
        rep_y, rep_x, rep_s = np.repeat(ys, cnt), np.repeat(xs, cnt), np.repeat(sign, cnt)
        k = np.concatenate([np.arange(c) for c in cnt])
        if flip_scan is not None:
            # Screen flip: rows update one after the other over one refresh
            # (16.7 ms), the pixel takes a few ms to respond, and successive
            # events of a pixel follow each other.
            ts = t_now + flip_scan[rep_y, rep_x] + k * 1500 + self.rng.exponential(2500, k.size)
        else:
            ts = t_prev + self.rng.uniform(0, max(1, t_now - t_prev), k.size)
        self.out.append((rep_x, rep_y, rep_s, ts.astype(np.int64)))

    def noise(self, t0, t1, rate_hz=0.3, hot=12):
        n = self.rng.poisson(rate_hz * W * H * (t1 - t0) * 1e-6)
        self.out.append((self.rng.integers(0, W, n), self.rng.integers(0, H, n),
                         self.rng.random(n) < 0.5, self.rng.integers(t0, t1, n)))
        hx, hy = self.rng.integers(0, W, hot), self.rng.integers(0, H, hot)
        for x, y in zip(hx, hy):
            m = self.rng.poisson(150 * (t1 - t0) * 1e-6)
            self.out.append((np.full(m, x), np.full(m, y), self.rng.random(m) < 0.7,
                             self.rng.integers(t0, t1, m)))

    def events(self):
        x = np.concatenate([o[0] for o in self.out]).astype(np.uint16)
        y = np.concatenate([o[1] for o in self.out]).astype(np.uint16)
        p = np.concatenate([o[2] for o in self.out])
        t = np.concatenate([o[3] for o in self.out]).astype(np.int64)
        order = np.argsort(t, kind="stable")
        return Events(x[order], y[order], p[order], t[order], W, H)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="output folder, e.g. sessions/sim")
    ap.add_argument("--poses", type=int, default=24)
    ap.add_argument("--hold-s", type=float, default=2.0)
    ap.add_argument("--move-s", type=float, default=0.8)
    ap.add_argument("--square-mm", type=float, default=70.0)
    ap.add_argument("--period-ms", type=int, default=400)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    sq = args.square_mm

    Kl, Dl = np.array(GT["K_left"]), np.array(GT["D_left"])
    Kr, Dr = np.array(GT["K_right"]), np.array(GT["D_right"])
    Rs = cv2.Rodrigues(np.array(GT["rvec"]))[0]
    Ts = np.array(GT["T"])
    rays = {"left": (subpixel_rays(Kl, Dl, 4), subpixel_rays(Kl, Dl, 2)),
            "right": (subpixel_rays(Kr, Dr, 4), subpixel_rays(Kr, Dr, 2))}

    poses = []
    while len(poses) < args.poses:
        rv, t = look_at_pose(rng, sq)
        R = cv2.Rodrigues(rv)[0]
        if board_visible(Kl, Dl, R, t, sq) and board_visible(Kr, Dr, Rs @ R, Rs @ t + Ts, sq):
            poses.append((rv, t))

    sensors = {"left": Sensor(rng), "right": Sensor(rng)}
    period = args.period_ms * 1000
    hold, move, step = int(args.hold_s * 1e6), int(args.move_s * 1e6), 10_000

    def cam_pose(side, rv, t):
        R = cv2.Rodrigues(rv)[0]
        return (R, t) if side == "left" else (Rs @ R, Rs @ t + Ts)

    def scan_delay(side, R, t):
        # Rows of the screen refresh top to bottom; map that onto the image.
        p = project(Kl if side == "left" else Kr, Dl if side == "left" else Dr, R, t, sq)
        top, bottom = p[:COLS].mean(0)[1], p[-COLS:].mean(0)[1]
        yy = np.repeat(np.arange(H, dtype=np.float64)[:, None], W, 1)
        frac = np.clip((yy - top) / max(1.0, bottom - top), -0.2, 1.2)
        return frac * 14000.0

    truth = {"poses": [], "square_mm": sq, **GT}
    now = 300_000
    state_b = False
    next_flip = period
    prev = poses[0]
    for side, sn in sensors.items():
        sn.step(render(rays[side][0], *cam_pose(side, *prev), state_b, sq), 0, now)

    for pi, pose in enumerate(poses):
        # --- move from the previous pose to this one -------------------------
        if pi > 0:
            n_steps = move // step
            for k in range(1, n_steps + 1):
                a = 0.5 - 0.5 * np.cos(np.pi * k / n_steps)
                rv = (1 - a) * prev[0] + a * pose[0]
                t = (1 - a) * prev[1] + a * pose[1]
                t_now = now + step
                while next_flip <= t_now:
                    state_b = not state_b
                    next_flip += period
                for side, sn in sensors.items():
                    sn.step(render(rays[side][1], *cam_pose(side, rv, t), state_b, sq), now, t_now)
                now = t_now
        # --- settle: re-render at full quality so the hold starts clean ------
        for side, sn in sensors.items():
            sn.step(render(rays[side][0], *cam_pose(side, *pose), state_b, sq), now, now + step)
        now += step
        # --- hold still; only flips produce events ---------------------------
        t_end = now + hold
        n_flips = 0
        while next_flip <= t_end:
            state_b = not state_b
            # small hand tremor between flips
            rv = pose[0] + rng.normal(0, 1.5e-4, 3)
            t = pose[1] + rng.normal(0, 0.15, 3)
            for side, sn in sensors.items():
                R, tc = cam_pose(side, rv, t)
                sn.step(render(rays[side][0], R, tc, state_b, sq), now, next_flip,
                        flip_scan=scan_delay(side, R, tc))
            now = next_flip
            next_flip += period
            n_flips += 1
        now = t_end
        Rl, tl = cam_pose("left", *pose)
        Rr, tr = cam_pose("right", *pose)
        truth["poses"].append({
            "t_start": int(t_end - hold), "t_end": int(t_end), "flips": n_flips,
            "left": project(Kl, Dl, Rl, tl, sq).tolist(),
            "right": project(Kr, Dr, Rr, tr, sq).tolist()})
        prev = pose
        print(f"pose {pi + 1}/{len(poses)} simulated", end="\r", flush=True)

    os.makedirs(args.session, exist_ok=True)
    for side, sn in sensors.items():
        sn.noise(0, now)
        ev = sn.events()
        save_npz(os.path.join(args.session, f"{side}.npz"), ev)
        print(f"\n{side}: {len(ev):,} events over {now / 1e6:.1f} s")
    with open(os.path.join(args.session, "ground_truth.json"), "w") as f:
        json.dump(truth, f)


if __name__ == "__main__":
    main()
