#!/usr/bin/env python3
"""Report section 5: event cameras against the RealSense in the dark (lab_test07).

    python report/s5_dark.py

A ball thrown around in almost full darkness; the light comes on at about 14 s, so
only 0-13.8 s is used. The ball moves around, so there is no fixed ball box:
- Event cameras: depth_events.py (defaults, noise filter 5 ms; --max-disp 200 because
  the ball comes closer than 0.8 m), then the ball per 50 ms step is the densest
  ball-wide group of matched events (tests/compare_ball_tracks.py).
- RealSense: realsense_ball.py --max-depth-m 2. The colour image is dark, so the ball
  is found in depth: a moving, ball-wide blob closer than the background.

Writes report/out/5_dark/: views.png (one moment as the cameras recorded it), tracks.png, table.md /
table.csv, data_used.md.
"""
import os
import re
import subprocess
import sys
from types import SimpleNamespace

import numpy as np

import common as c
from common import plt
from compare_ball_tracks import event_track, load_matched_events, load_realsense, pair_tracks

RECORDING = os.path.join(c.LAB, "lab_test07")
START_S, DURATION_S = 0.0, 13.8
MAX_DISP = 200
VIEW_T_S = 2.5          # the moment shown in views.png (dotted line in tracks.png)


def run_once(cmd, out, log_name):
    log = os.path.join(out, log_name)
    if not os.path.exists(log):
        os.makedirs(out, exist_ok=True)
        text = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        with open(log, "w") as f:
            f.write(" ".join(cmd) + "\n\n" + text)
    return open(log).read()


def main():
    folder = c.out_dir("5_dark")
    events_out, rs_out = os.path.join(folder, "events"), os.path.join(folder, "realsense")
    log = run_once([sys.executable, os.path.join(c.ROOT, "depth_events.py"), RECORDING, "--config", c.CONFIG,
                    "--row-shift", str(c.ROW_SHIFT), "--max-disp", str(MAX_DISP), "--out", events_out],
                   events_out, "log.txt")
    compute = float(re.search(r"([\d.]+) s of computing per second", log).group(1))
    run_once([sys.executable, os.path.join(c.ROOT, "realsense_ball.py"), RECORDING, "--max-depth-m", "2",
              "--out", rs_out], rs_out, "log.txt")

    args = SimpleNamespace(step_ms=c.STEP_MS, window_ms=c.WINDOW_MS, cell_px=8, min_events=30,
                           focal_px=c.StereoCalib(c.CONFIG).focal_px, ball_radius_m=0.0335)
    ev = load_matched_events(events_out)
    rs_t, rs_z = load_realsense(rs_out)
    keep = (rs_t >= START_S) & (rs_t <= START_S + DURATION_S)
    rs_t, rs_z = rs_t[keep], rs_z[keep]
    steps, track = event_track(ev, START_S, START_S + DURATION_S, args)
    pairs = pair_tracks(rs_t, rs_z, track, max_gap_s=0.04)
    diff = np.array([p["difference_pct"] for p in pairs])

    c.write_table(folder, [dict(
        steps=len(steps), ev_steps=len(track), rs_frames=rs_z.size, pairs=len(pairs),
        median_diff=float(np.median(diff)), within10=100 * float(np.mean(np.abs(diff) <= 10)), compute=compute)], [
        ("steps", "Event steps (50 ms)", "{}"), ("ev_steps", "Steps with a ball (events)", "{}"),
        ("rs_frames", "RealSense frames with a ball", "{}"), ("pairs", "Frames found by both (within 40 ms)", "{}"),
        ("median_diff", "Events vs RealSense (median)", "{:+.1f} %"), ("within10", "Within ±10 %", "{:.0f} %"),
        ("compute", "Event matching: compute per s", "{:.2f} s")])
    figure_tracks(folder, rs_t, rs_z, track)
    c.raw_frame(folder, "views", RECORDING, VIEW_T_S, c.WINDOW_MS, "lab_test07 in the dark")
    c.write_data_used(folder, f"""
# Data used: section 5, the dark recording

Recording: `{RECORDING}` (event cameras .npz, RealSense `_realsense.db3`), {START_S:g}-{START_S + DURATION_S:g} s
(the light comes on at about 14 s). Calibration `{c.CONFIG}`, row shift {c.ROW_SHIFT:g}.

This recording has no `_info.json`, so the RealSense time comes from the start second in the
`.raw` header (realsense_ball.py; good to about ±0.5 s). The two tracks line up within a frame
on three throws, so the real error is much smaller.

Commands (also in `events/log.txt` and `realsense/log.txt`):
- `depth_events.py lab_test07 --config ... --row-shift {c.ROW_SHIFT:g} --max-disp {MAX_DISP}` (noise filter
  {c.NOISE_FILTER_MS:g} ms by default)
- `realsense_ball.py lab_test07 --max-depth-m 2`
- ball in the events per {c.STEP_MS:g} ms step from the last {c.WINDOW_MS:g} ms: tests/compare_ball_tracks.py's
  event_track (8 px cells, at least 30 matched events, about one ball wide)
- pairs: each ok RealSense ball with the nearest event ball within 40 ms

There is no ground truth here: the comparison shows where the two sensors agree, and where
only one of them reports a ball. views.png: {VIEW_T_S:g} s, as recorded.
""")


def figure_tracks(folder, rs_t, rs_z, track):
    fig, ax = plt.subplots(figsize=(10, 3.4))
    ax.plot(rs_t, rs_z, "s", ms=4, mfc="none", color="tab:orange", label="RealSense (depth frames, 15 fps)")
    ax.plot([b["t_s"] for b in track], [b["depth_m"] for b in track], ".", ms=4, color="tab:blue",
            label="event cameras (50 ms steps)")
    ax.axvline(VIEW_T_S, color="0.6", lw=0.6, ls=":")
    ax.set_ylim(0, 3)
    ax.set_xlabel("time [s] (dotted: the moment in views.png)")
    ax.set_ylabel("distance to the ball [m]")
    ax.set_title("lab_test07, ball thrown in the dark", loc="left")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    c.save(fig, folder, "tracks")




if __name__ == "__main__":
    main()
