#!/usr/bin/env python3
"""Ball distance over time from the event cameras and from the RealSense, side by side.

    python depth_events.py <recording> --config <config> --row-shift -2 --max-disp 200 \\
        --out <recording>_depth_events
    python realsense_ball.py <recording> --max-depth-m 2
    python tests/compare_ball_tracks.py <recording> [--start-s 0 --duration-s 13.8]

For a ball that moves around without a fixed box (lab_test07, thrown in the dark).

The ball in the events, per step (--step-ms, window --window-ms), from the matched
events in depth_events.py's events.npz:
1. the --cell-px grid cell whose 3 x 3 neighbourhood holds the most matched events;
2. of those events, the ones within 15 % of their median depth (noise matches have
   random depths); at least --min-events must be left;
3. the group must be about one ball wide at that depth (as in realsense_ball.py).
Its distance is the median depth of the group.

Writes to --out (default <recording>_ball_tracks/):
- events_ball.csv   t_s, x, y (rectified left pixel), depth_m, events
- pairs.csv         every ok RealSense ball with an event ball within --max-gap-ms:
                    t_s, realsense_m, events_m, difference_pct
- tracks.png        both distances over time
and prints how often each sensor found a ball and how well they agree where both did.
There is no ground truth for when the ball is in view, so "found" counts what each
method reports, right or wrong; tracks.png shows whether both follow the same throws.
"""
import argparse
import csv
import os

import numpy as np


def load_matched_events(folder):
    """The matched events of depth_events.py's events.npz, sorted by time."""
    d = np.load(os.path.join(folder, "events.npz"))
    matched = (d["status"] == 4) & np.isfinite(d["depth_m"])
    order = np.argsort(d["t_us"][matched], kind="stable")
    return {k: d[k][matched][order] for k in ("t_us", "x", "y", "depth_m")}


def load_realsense(folder):
    """Times and distances of the ok rows of realsense_ball.py's ball.csv."""
    rows = [r for r in csv.DictReader(open(os.path.join(folder, "ball.csv"))) if r["ok"] == "1"]
    return np.array([float(r["t_s"]) for r in rows]), np.array([float(r["centre_m"]) for r in rows])


def event_ball(ev, t0_us, t1_us, args):
    """The ball in the matched events of [t0_us, t1_us): dict(x, y, depth_m, events) or None."""
    i0, i1 = np.searchsorted(ev["t_us"], [t0_us, t1_us])
    x, y, z = ev["x"][i0:i1], ev["y"][i0:i1], ev["depth_m"][i0:i1]
    if x.size < args.min_events:
        return None

    # 1. Densest 3 x 3 block of grid cells.
    cx, cy = (x / args.cell_px).astype(int) + 1, (y / args.cell_px).astype(int) + 1   # +1: room for the border
    counts = np.zeros((cy.max() + 2, cx.max() + 2))
    np.add.at(counts, (cy, cx), 1)
    block = sum(np.roll(np.roll(counts, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    by, bx = np.unravel_index(np.argmax(block), block.shape)
    group = (np.abs(cx - bx) <= 1) & (np.abs(cy - by) <= 1)
    if group.sum() < args.min_events:
        return None

    # 2. Only the events at about the group's depth.
    group &= np.abs(z - np.median(z[group])) < 0.15 * np.median(z[group])
    if group.sum() < args.min_events:
        return None

    # 3. About one ball wide.
    depth = float(np.median(z[group]))
    diameter = 2 * args.focal_px * args.ball_radius_m / depth
    width = min(np.ptp(np.percentile(x[group], [10, 90])), np.ptp(np.percentile(y[group], [10, 90])))
    if width > 1.6 * diameter:
        return None
    return dict(x=float(np.median(x[group])), y=float(np.median(y[group])), depth_m=depth, events=int(group.sum()))


def event_track(ev, t0, t1, args):
    """Event ball per step: (step times, rows with t_s at the middle of each window)."""
    window = args.window_ms / 1e3
    steps = np.arange(t0 + window, t1, args.step_ms / 1e3)
    track = []
    for t in steps:
        ball = event_ball(ev, (t - window) * 1e6, t * 1e6, args)
        if ball:
            track.append(dict(t_s=t - window / 2, **ball))
    return steps, track


def pair_tracks(rs_t, rs_z, track, max_gap_s):
    """Every RealSense ball with an event ball at most max_gap_s away."""
    if not track:
        return []
    ev_t = np.array([b["t_s"] for b in track])
    pairs = []
    for t, z in zip(rs_t, rs_z):
        k = int(np.argmin(np.abs(ev_t - t)))
        if abs(ev_t[k] - t) <= max_gap_s:
            ze = track[k]["depth_m"]
            pairs.append(dict(t_s=t, realsense_m=z, events_m=ze, difference_pct=100 * (ze - z) / z))
    return pairs


def write_csv(path, rows, fields, formats):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows([[fmt % r[k] for k, fmt in zip(fields, formats)] for r in rows])


def plot(path, title, rs_t, rs_z, track, args):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(rs_t, rs_z, "s", ms=4, mfc="none", color="tab:orange", label="RealSense (depth frames, 15 fps)")
    ev_t, ev_z = np.array([b["t_s"] for b in track]), np.array([b["depth_m"] for b in track])
    ax.plot(ev_t, ev_z, ".", ms=4, color="tab:blue", label=f"event cameras ({args.step_ms:g} ms steps)")
    ax.set_ylim(0, args.plot_max_m)
    beyond = int((ev_z > args.plot_max_m).sum())
    if beyond:
        ax.text(0.01, 0.95, f"{beyond} event points above {args.plot_max_m:g} m not shown",
                transform=ax.transAxes, fontsize=7, va="top")
    ax.set_xlabel("time [s]")
    ax.set_ylabel("distance to ball [m]")
    ax.set_title(title, loc="left", fontsize=9)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="prefix, as for realsense_ball.py")
    ap.add_argument("--events", default=None, help="depth_events.py output folder (default <recording>_depth_events)")
    ap.add_argument("--realsense", default=None, help="realsense_ball.py output folder")
    ap.add_argument("--out", default=None, help="output folder (default <recording>_ball_tracks)")
    ap.add_argument("--start-s", type=float, default=None)
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--step-ms", type=float, default=50)
    ap.add_argument("--window-ms", type=float, default=20)
    ap.add_argument("--cell-px", type=int, default=8)
    ap.add_argument("--min-events", type=int, default=30)
    ap.add_argument("--focal-px", type=float, default=347.66, help="rectified focal length (depth_events.py prints it)")
    ap.add_argument("--ball-radius-m", type=float, default=0.0335)
    ap.add_argument("--max-gap-ms", type=float, default=40, help="pair a RealSense frame with an event step this close")
    ap.add_argument("--plot-max-m", type=float, default=3.0, help="top of the plot's distance axis")
    args = ap.parse_args()
    rec = os.path.expanduser(args.recording)
    out = args.out or rec + "_ball_tracks"
    os.makedirs(out, exist_ok=True)

    ev = load_matched_events(args.events or rec + "_depth_events")
    rs_t, rs_z = load_realsense(args.realsense or rec + "_realsense_ball")

    t0, t1 = ev["t_us"][0] / 1e6, ev["t_us"][-1] / 1e6
    if args.start_s is not None:
        t0 = max(t0, args.start_s)
    if args.duration_s is not None:
        t1 = min(t1, t0 + args.duration_s)
    inside = (rs_t >= t0) & (rs_t <= t1)
    rs_t, rs_z = rs_t[inside], rs_z[inside]

    steps, track = event_track(ev, t0, t1, args)
    pairs = pair_tracks(rs_t, rs_z, track, args.max_gap_ms / 1e3)
    write_csv(os.path.join(out, "events_ball.csv"), track, ["t_s", "x", "y", "depth_m", "events"],
              ["%.4f", "%.1f", "%.1f", "%.3f", "%d"])
    write_csv(os.path.join(out, "pairs.csv"), pairs, ["t_s", "realsense_m", "events_m", "difference_pct"],
              ["%.4f", "%.3f", "%.3f", "%+.1f"])
    plot(os.path.join(out, "tracks.png"), os.path.basename(rec), rs_t, rs_z, track, args)

    print(f"{t0:.2f}-{t1:.2f} s: events found a ball in {len(track)} of {len(steps)} steps "
          f"({100 * len(track) / max(len(steps), 1):.0f} %), RealSense in {len(rs_t)} depth frames (ok rows)")
    if pairs:
        d = np.array([p["difference_pct"] for p in pairs])
        print(f"{len(pairs)} RealSense frames with an event ball within {args.max_gap_ms:g} ms: difference "
              f"events - RealSense median {np.median(d):+.1f} %, within ±10 %: {100 * np.mean(np.abs(d) <= 10):.0f} %")
    print("wrote", out)


if __name__ == "__main__":
    main()
