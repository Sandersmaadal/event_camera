#!/usr/bin/env python3
"""Report section 3: event cameras against the RealSense on the lab ball tests.

    python report/s2_matching.py      # first: makes the event-by-event runs used here
    python report/s3_realsense.py

The best method of sections 1-2 (event-by-event matching) against the RealSense D435,
which sits on the same line as the event cameras, just right of the right camera, so
both measure depth from the same plane.

- Event cameras: median depth of the matched points in the ball box per 50 ms step
  (the runs of section 2).
- RealSense: distance to the ball's centre in each depth frame (realsense_ball.py:
  the colour image says where the ball is, the depth image is searched nearby for the
  most uniform ball-sized disc; tennis ball radius 33.5 mm assumed). Only frames
  marked ok (consistent with the frames around them).
- Each event step is compared with the nearest RealSense frame, if one is within 70 ms.

Writes report/out/3_realsense/: views.png (one moment as the cameras recorded it),
depth_over_time.png, table.md / table.csv, data_used.md.
"""
import csv
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

import common as c
from common import plt
from evaluate_lab import run

MAX_GAP_S = 0.07
VIEW_TEST, VIEW_T_S = "lab_test02", 4.6      # the moment shown in views.png


def realsense_track(test, folder):
    """RealSense ball distances (t in s of event time, centre_m) of the ok frames, and all rows."""
    out = os.path.join(folder, "realsense", test)
    if not os.path.exists(os.path.join(out, "ball.csv")):
        subprocess.run([sys.executable, os.path.join(c.ROOT, "realsense_ball.py"), os.path.join(c.LAB, test),
                        "--out", out], check=True)
    rows = list(csv.DictReader(open(os.path.join(out, "ball.csv"))))
    ok = [r for r in rows if r["ok"] == "1"]
    return np.array([float(r["t_s"]) for r in ok]), np.array([float(r["centre_m"]) for r in ok]), rows


def event_steps(test, args):
    """Event-by-event depth in the ball box: step times (s of event time) and median depth per step."""
    spec = c.TESTS[test]
    x0, y0, x1, y1 = spec["roi"]
    times, medians = [], []
    for rng in spec["times"]:
        out, _ = run("events", test, rng, args)
        d = np.load(os.path.join(out, "depth.npz"))
        inside = (d["x"] >= x0) & (d["x"] < x1) & (d["y"] >= y0) & (d["y"] < y1) & np.isfinite(d["depth_m"])
        for k in np.unique(d["frame"][inside]):
            z = d["depth_m"][inside & (d["frame"] == k)]
            # The middle of the step's window, as the RealSense time it is compared with.
            times.append((d["times_us"][k] - c.WINDOW_MS * 500) / 1e6)
            medians.append(float(np.median(z)))
    return np.array(times), np.array(medians)


def pair(ev_t, ev_z, rs_t, rs_z):
    """(event depth, RealSense depth) for every event step with a RealSense frame within MAX_GAP_S."""
    pairs = []
    for t, z in zip(ev_t, ev_z):
        k = int(np.argmin(np.abs(rs_t - t)))
        if abs(rs_t[k] - t) <= MAX_GAP_S:
            pairs.append((z, rs_z[k]))
    return np.array(pairs).reshape(-1, 2)


def main():
    folder = c.out_dir("3_realsense")
    args = SimpleNamespace(data=c.LAB, config=c.CONFIG, out=c.out_dir("2_matching"), rerun=False,
                           row_shift=c.ROW_SHIFT, max_disp=c.MAX_DISP)
    rows, tracks = [], {}
    for test, spec in c.TESTS.items():
        rs_t, rs_z, _ = realsense_track(test, folder)
        # Only the RealSense frames inside the test's time ranges.
        keep = np.zeros(rs_t.size, bool)
        for a, b in spec["times"]:
            keep |= (rs_t >= a) & (rs_t <= b)
        rs_t, rs_z = rs_t[keep], rs_z[keep]
        ev_t, ev_z = event_steps(test, args)
        tracks[test] = (ev_t, ev_z, rs_t, rs_z)
        p = pair(ev_t, ev_z, rs_t, rs_z)
        diff = 100 * (p[:, 0] - p[:, 1]) / p[:, 1]
        truth = spec["truth_m"]
        rows.append(dict(test=test, truth_m=truth, rs_frames=rs_z.size, rs_median_m=float(np.median(rs_z)),
                         rs_vs_tape_pct=100 * (np.median(rs_z) - truth) / truth,
                         ev_steps=ev_z.size, ev_median_m=float(np.median(ev_z)),
                         ev_vs_tape_pct=100 * (np.median(ev_z) - truth) / truth,
                         pairs=len(p), ev_vs_rs_pct=float(np.median(diff)),
                         within5_pct=100 * float(np.mean(np.abs(diff) <= 5))))

    c.write_table(folder, rows, [
        ("test", "Test", "{}"), ("truth_m", "Tape", "{:.0f} m"),
        ("rs_median_m", "RealSense median", "{:.3f} m"), ("rs_vs_tape_pct", "RealSense vs tape", "{:+.1f} %"),
        ("ev_median_m", "Event cameras median", "{:.3f} m"), ("ev_vs_tape_pct", "Events vs tape", "{:+.1f} %"),
        ("pairs", "Steps with both", "{}"), ("ev_vs_rs_pct", "Events vs RealSense (median)", "{:+.1f} %"),
        ("within5_pct", "Steps within ±5 % of RealSense", "{:.0f} %")])
    c.raw_frame(folder, "views", os.path.join(c.LAB, VIEW_TEST), VIEW_T_S, c.WINDOW_MS,
                f"{VIEW_TEST}, ball at {c.TESTS[VIEW_TEST]['truth_m']:g} m")
    figure_depth_over_time(folder, tracks)
    c.write_data_used(folder, f"""
# Data used: section 3, event cameras against the RealSense

Recordings: `{c.LAB}/lab_test01`, `lab_test02`, `lab_test03`: the event cameras (left/right .npz)
and the RealSense (`*_realsense.db3`: depth 1280 x 720 and colour 640 x 480 at 15 fps), on the
same clock through the clock anchor in `*_info.json`.

Event cameras: the event-by-event runs of section 2 (`../2_matching/runs/*_events/`), median
depth of the points in the ball box per step. Ball boxes and time ranges as in section 2.

RealSense: `realsense_ball.py` (default settings), output in `realsense/<test>/ball.csv` (with a
crop of every frame there if run with `--sheet`). Ok frames inside the time ranges only.

Pairing: each event step (middle of its {c.WINDOW_MS:g} ms window) with the nearest RealSense frame
within {MAX_GAP_S * 1000:.0f} ms. views.png: {VIEW_TEST} at {VIEW_T_S:g} s, as recorded.
""")




def figure_depth_over_time(folder, tracks):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2))
    for ax, (test, (ev_t, ev_z, rs_t, rs_z)) in zip(axes, tracks.items()):
        truth = c.TESTS[test]["truth_m"]
        ax.plot(rs_t, rs_z, "s", ms=4, mfc="none", color="tab:orange", label="RealSense (15 fps)")
        ax.plot(ev_t, ev_z, ".", ms=4, color="tab:blue", label="event cameras (50 ms steps)")
        ax.axhline(truth, color="k", lw=0.8, ls="--", label="tape")
        ax.set_ylim(truth * 0.85, truth * 1.15)
        ax.set_title(f"{test}: ball at {truth:g} m")
        ax.set_xlabel("time from the start [s]")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("distance to the ball [m]")
    axes[0].legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    c.save(fig, folder, "depth_over_time")


if __name__ == "__main__":
    main()
