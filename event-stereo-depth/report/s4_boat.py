#!/usr/bin/env python3
"""Report section 4: depth of the boat Buster against GNSS (experiment 2, cameras on land).

    python report/s4_boat.py [--config <harbour calibration>/config --row-shift <rows>]

Experiment 2 (2026-10-19): the cameras stood still on land; Buster drove past at
12-20 m. Its position comes from its GNSS receiver (1 Hz, standalone); the cameras'
position from the same receiver standing 45 cm behind them before the tests
(data_collection/gnss/, made by gnss/extract_gnss.py).

1. Time: the camera laptop's clock was about 19 h 41 min off, known only to about
   +-30 s. Buster's direction seen from the cameras is known twice: from GNSS, and
   from its column in the event image. The clock offset is the one where the two agree
   best (the camera's viewing direction is fitted at the same time).
2. Depth: depth_events.py; per second, the median depth of the matched events on
   Buster (the rows of the hull, the columns around Buster's centre found in step 1).
3. GNSS depth: Buster's antenna relative to the cameras, along the viewing direction.

Writes report/out/4_boat/: views.png (one moment as the cameras recorded it),
sync.png, depth_over_time.png (GNSS, RealSense and event cameras), table.md / table.csv,
data_used.md.
"""
import argparse
import csv
import json
import os
import subprocess
import sys

import cv2
import numpy as np

import common as c
from common import plt
from evdepth.realsense import RealSense

RECORDING = os.path.join(c.DATA, "recordings", "datacololection_test02")
GNSS = os.path.join(c.DATA, "gnss", "exp2", "relative.csv")    # Buster east/north of the camera receiver
RECEIVER_BEHIND_M = 0.45          # the receiver stood this far behind the cameras
IN_VIEW_S = (9.5, 31.5)           # Buster in the event image (s from the start)
HULL_ROWS = (90, 230)             # rectified rows of Buster's hull and cabin
STEP_S = 0.5                      # time step of the image direction
VIEW_T_S = 18.0               # the moment shown in views.png


def gnss_track():
    rows = list(csv.DictReader(open(GNSS)))
    return {k: np.array([float(r[k]) for r in rows]) for k in ("t_utc_s", "east_m", "north_m")}


def event_clock_to_system_s(recording):
    a = json.load(open(recording + "_info.json"))["event_clock_anchor"]
    return lambda t_us: (np.asarray(t_us) - a["event_time_us"] + a["system_time_us"]) / 1e6


# ---------------------------------------------------------------------------- 1. time sync

def buster_columns(win, start_us):
    """Buster's centre column every STEP_S: events above the per-column background in the hull rows."""
    t = (win.t - start_us) / 1e6
    rows = (win.y > HULL_ROWS[0]) & (win.y < HULL_ROWS[1])
    bins = np.arange(0, t.max(), STEP_S)
    edges = np.arange(0, win.width + 1, 4)
    counts, _, _ = np.histogram2d(t[rows], win.x[rows], [bins, edges])
    background = np.median(counts, axis=0)
    track = []
    for k in range(len(bins) - 1):
        mid = bins[k] + STEP_S / 2
        excess = np.clip(counts[k] - 3 * background - 5, 0, None)
        if IN_VIEW_S[0] < mid < IN_VIEW_S[1] and excess.sum() > 1500:
            track.append((mid, float((excess * (edges[:-1] + 2)).sum() / excess.sum())))
    return np.array(track)


def fit_clock(track_t_sys, image_bearing, gnss):
    """Clock offset (real = camera + offset) and camera axis bearing where GNSS and image agree best."""
    lo, hi = gnss["t_utc_s"][0] - track_t_sys[0], gnss["t_utc_s"][-1] - track_t_sys[-1]
    best = None
    for offset in np.arange(np.ceil(lo), hi, 0.1):
        t = track_t_sys + offset
        bearing = np.arctan2(np.interp(t, gnss["t_utc_s"], gnss["east_m"]),
                             np.interp(t, gnss["t_utc_s"], gnss["north_m"]))
        diff = bearing - image_bearing
        axis = np.angle(np.exp(1j * diff).mean())
        rms = np.sqrt(np.mean(np.angle(np.exp(1j * (diff - axis))) ** 2))
        if best is None or rms < best["rms"]:
            best = dict(offset=offset, axis=axis, rms=rms)
    return best


# ---------------------------------------------------------------------------- 2. and 3. depth

def gnss_depth(t_utc, gnss, axis):
    """Distance from the cameras to Buster's antenna along the viewing direction, and the range."""
    e = np.interp(t_utc, gnss["t_utc_s"], gnss["east_m"])
    n = np.interp(t_utc, gnss["t_utc_s"], gnss["north_m"])
    along = e * np.sin(axis) + n * np.cos(axis) - RECEIVER_BEHIND_M
    return along, np.hypot(e, n)


def event_depth_per_second(events, to_sys, start_sys, columns):
    """Median depth of the matched events on Buster, per second."""
    m = (events["status"] == 4) & np.isfinite(events["depth_m"])
    m &= (events["y"] > HULL_ROWS[0]) & (events["y"] < HULL_ROWS[1])
    t = to_sys(events["t_us"][m]) - start_sys
    x, z = events["x"][m], events["depth_m"][m]
    rows = []
    for s in np.arange(np.ceil(IN_VIEW_S[0]), IN_VIEW_S[1] - 1):
        centre = np.interp(s + 0.5, columns[:, 0], columns[:, 1])
        k = (t >= s) & (t < s + 1) & (np.abs(x - centre) < 60)     # Buster is about 120 px long here
        if k.sum() >= 20:
            rows.append(dict(t_s=s + 0.5, events_m=float(np.median(z[k])), q1=float(np.percentile(z[k], 25)),
                             q3=float(np.percentile(z[k], 75)), points=int(k.sum())))
    return rows


def realsense_depth_per_second(rs, zero_us, start_us):
    """Median RealSense depth of the biggest blob closer than the background (Buster), per second.
    Background: the median depth of the first 8 s, before Buster comes into view."""
    t = (rs.depth_times_us - zero_us - start_us) / 1e6
    background = np.median(np.stack([rs.depth(i) for i in np.where(t < 8)[0][::2]]), axis=0)
    rows = {}
    for s in np.arange(np.ceil(IN_VIEW_S[0]), IN_VIEW_S[1] - 1):
        values = []
        for i in np.where((t >= s) & (t < s + 1))[0]:
            d = rs.depth(i)
            near = (d > 2) & (d < 25) & ((background == 0) | (background - d > 1.5))
            near = cv2.morphologyEx(near.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            n, labels, stats, _ = cv2.connectedComponentsWithStats(near)
            if n > 1:
                values.append(np.median(d[labels == 1 + np.argmax(stats[1:, 4])]))
        if values:
            rows[s + 0.5] = float(np.median(values))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=c.CONFIG, help="calibration (default: the lab one, see data_used.md)")
    ap.add_argument("--row-shift", type=float, default=-6.0, help="measured with check_rectification.py")
    args = ap.parse_args()
    folder = c.out_dir("4_boat")
    calib = c.StereoCalib(args.config)
    rect_l, _ = c.make_rectifiers(calib)
    gnss = gnss_track()
    to_sys = event_clock_to_system_s(RECORDING)

    # 1. Time sync from Buster's direction.
    ev_l, ev_r = c.load_pair(RECORDING)
    win = c.rectify_window(ev_l, rect_l, ev_l.t[0], ev_l.t[-1])
    columns = buster_columns(win, ev_l.t[0])
    start_sys = float(to_sys(ev_l.t[0]))
    image_bearing = np.arctan((columns[:, 1] - calib.P1[0, 2]) / calib.focal_px)
    sync = fit_clock(start_sys + columns[:, 0], image_bearing, gnss)

    # 2. Event depth.
    out = os.path.join(folder, "events")
    if not os.path.exists(os.path.join(out, "events.npz")):
        cmd = [sys.executable, os.path.join(c.ROOT, "depth_events.py"), RECORDING, "--config", args.config,
               "--row-shift", str(args.row_shift), "--max-disp", "64", "--start-s", str(IN_VIEW_S[0]),
               "--duration-s", str(IN_VIEW_S[1] - IN_VIEW_S[0]), "--out", out]
        text = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
        with open(os.path.join(out, "log.txt"), "w") as f:
            f.write(" ".join(cmd) + "\n\n" + text)
    rows = event_depth_per_second(np.load(os.path.join(out, "events.npz")), to_sys, start_sys, columns)

    # 3. GNSS depth at the same moments, and the RealSense's distance to Buster.
    a = json.load(open(RECORDING + "_info.json"))["event_clock_anchor"]
    rs_depth = realsense_depth_per_second(RealSense(RECORDING + "_realsense.db3"),
                                          a["system_time_us"] - a["event_time_us"], ev_l.t[0])
    for r in rows:
        along, rng = gnss_depth(start_sys + r["t_s"] + sync["offset"], gnss, sync["axis"])
        r.update(gnss_m=float(along), range_m=float(rng), realsense_m=rs_depth.get(r["t_s"]))

    c.write_table(folder, rows, [
        ("t_s", "Time [s]", "{:.1f}"), ("gnss_m", "GNSS", "{:.1f} m"), ("realsense_m", "RealSense", "{:.1f} m"),
        ("events_m", "Event cameras", "{:.1f} m"), ("points", "Matched events", "{}")])
    figure_sync(folder, columns, image_bearing, start_sys, sync, gnss)
    lab = os.path.samefile(args.config, c.CONFIG)
    figure_depth(folder, rows, "lab, 28 Oct (does not fit the harbour rig)" if lab else args.config)
    c.raw_frame(folder, "views", RECORDING, VIEW_T_S, 50, "Experiment 2, Buster drives past")
    with open(os.path.join(folder, "sync.json"), "w") as f:
        json.dump(dict(clock_offset_s=sync["offset"], camera_axis_bearing_deg=float(np.degrees(sync["axis"]) % 360),
                       rms_deg=float(np.degrees(sync["rms"]))), f, indent=2)
    c.write_data_used(folder, f"""
# Data used: section 4, the boat (experiment 2)

Recording: `{RECORDING}` (event cameras and RealSense), {IN_VIEW_S[0]:g}-{IN_VIEW_S[1]:g} s, while Buster is
in view. Cameras standing still on land.

GNSS: `{GNSS}` (gnss/extract_gnss.py): Buster's standalone 1 Hz fixes relative to the median
position of the same receiver standing {RECEIVER_BEHIND_M:g} m behind the cameras (pretest-capture and
test0, 1447 fixes, spread 0.25 m). Standalone fixes can be off by 1-2 m; much of that is shared
by both positions, because they come from the same receiver about 30 minutes apart.

Time: clock offset {sync['offset']:.1f} s (real UTC = camera system time + offset), fitted from
Buster's direction (image column against GNSS bearing, rms {np.degrees(sync['rms']):.1f} deg); offsets 1 s
either side fit almost as well, so about ±1 s, which is ±0.4 m of Buster's distance. Camera viewing
direction from the same fit: {np.degrees(sync['axis']) % 360:.1f} deg from north.

Calibration: `{args.config}`, row shift {args.row_shift:g} (check_rectification.py on 10-31 s gives a median of
-5.9 rows with the lab calibration).{'''

**The lab calibration does not fit this recording.** The rows are off by about 6 (a camera
turned about 1 deg after this recording or before the lab calibration). A sideways turn of
the same size would bias the depth, and this check cannot see it. With the lab calibration
the event cameras put Buster at 8-10 m, the RealSense at 12-14 m and GNSS at 16-19 m
(10-20 s). Use the harbour calibration (recordings/calibration, 2026-10-19) for the event
depth. The GNSS distance is also in doubt: the RealSense sees Buster pass in front of the
mooring pole (about 16 m away by the RealSense), while the GNSS distance puts it behind, and
Buster's size in the colour image (31 deg at 18 s, almost broadside) fits a 5-6 m boat at about
10-12 m, not at 17 m. The receiver stood 45 cm behind the cameras as assumed, so the likely
cause is the standalone fixes themselves (the camera spot is next to a large building, which
can bias a standalone fix by metres); post-processing the raw .ubx logs would show it.'''if lab else ''}

RealSense: per second, the median depth of the biggest blob closer than the background (the median
of the first 8 s, before Buster is in view) by at least 1.5 m; that blob is Buster.

Depth: `depth_events.py` with the defaults (noise filter {c.NOISE_FILTER_MS:g} ms), --max-disp 64. Per second,
the median depth of the matched events in rows {HULL_ROWS[0]}-{HULL_ROWS[1]} within 60 px of Buster's centre
column. GNSS depth: Buster's antenna along the viewing direction, minus {RECEIVER_BEHIND_M:g} m.

The antenna is inside the boat, but the event cameras see mostly the outside of the hull (its
edges, on the side facing the cameras). So the event depth should be shorter than the GNSS
depth: by about half the beam (about 1 m) when Buster is broadside, and up to about half its
length when it is turned towards the cameras (here 120-140 deg between its heading and the
line of sight, so up to about 2 m).
""")


def figure_sync(folder, columns, image_bearing, start_sys, sync, gnss):
    t = start_sys + columns[:, 0] + sync["offset"]
    gnss_bearing = np.arctan2(np.interp(t, gnss["t_utc_s"], gnss["east_m"]), np.interp(t, gnss["t_utc_s"], gnss["north_m"]))
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.plot(columns[:, 0], np.degrees(gnss_bearing), "-", color="k", label="GNSS bearing (after the clock fit)")
    ax.plot(columns[:, 0], np.degrees(image_bearing + sync["axis"]), ".", color="tab:blue",
            label="bearing from Buster's column in the event image")
    ax.set_xlabel("time from the start of the recording [s]")
    ax.set_ylabel("direction to Buster [deg from north]")
    ax.set_title(f"Clock offset {sync['offset']:.1f} s, rms {np.degrees(sync['rms']):.1f} deg", loc="left")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    c.save(fig, folder, "sync")


def figure_depth(folder, rows, calibration_label):
    t = [r["t_s"] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.plot(t, [r["gnss_m"] for r in rows], "-", color="k", label="GNSS (antenna, along the viewing direction)")
    ax.plot([r["t_s"] for r in rows if r["realsense_m"]], [r["realsense_m"] for r in rows if r["realsense_m"]],
            "s", ms=4, mfc="none", color="tab:orange", label="RealSense (median over Buster)")
    ax.errorbar(t, [r["events_m"] for r in rows], yerr=[[r["events_m"] - r["q1"] for r in rows],
                [r["q3"] - r["events_m"] for r in rows]], fmt=".", color="tab:blue", ms=5, lw=0.8,
                label="event cameras (median and quartiles per second)")
    ax.set_title(f"Calibration: {calibration_label}", loc="left")
    ax.set_ylim(0, 25)
    ax.set_xlabel("time from the start of the recording [s]")
    ax.set_ylabel("distance to Buster [m]")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)
    fig.tight_layout()
    c.save(fig, folder, "depth_over_time")




if __name__ == "__main__":
    main()
