#!/usr/bin/env python3
"""Report section 1: comparison of event representations.

    python report/s1_representations.py

Six ways to turn a 20 ms window of events into an image, each matched the same way
(windowed block matching with the census cost, as depth.py) on the three lab ball
tests, and compared with the tape distance:

- count       events per pixel
- count_pol   events per pixel, ON and OFF in separate channels
- ts          exponential time surface: exp(-age / 10 ms) of the latest event per pixel
- ts_linear   linear time surface: 1 - age / window
- ts_pol      exponential time surface, ON and OFF in separate channels
- voxel       the window cut into 3 time bins, ON = +1 and OFF = -1, spread linearly
              over the two nearest bins

count and voxel are in evdepth/representation.py; the other four were removed from
the main code after this comparison and are defined here, as they were.

Writes report/out/1_representations/: representations.png (the raw events and every
representation at one moment of the 2 m ball), table.md / table.csv, data_used.md.
"""
import os
import time

import numpy as np

import common as c
from common import plt
from evdepth.matching import MatchParams, match
from evdepth.representation import ReprParams, count_frame, event_count, voxel_grid, _nearest, _subset

TAU_US = 10_000.0           # decay of the exponential time surfaces
FIGURE_TEST, FIGURE_T_S = "lab_test02", 4.6     # the moment shown in the figure


# ---------------------------------------------------------------------------- the four removed representations

def last_event_time(win):
    """Time of the latest event per pixel, -inf where there was none."""
    xi, yi = _nearest(win)
    last = np.full((win.height, win.width), -np.inf)
    last[yi, xi] = win.t.astype(np.float64)       # events are sorted, so the latest one stays
    return last


def time_surface(win, p):
    age = win.t_end - last_event_time(win)
    return np.exp(-age / TAU_US).astype(np.float32)[None]


def time_surface_linear(win, p):
    age = win.t_end - last_event_time(win)
    return np.clip(1.0 - age / max(win.t_end - win.t_start, 1.0), 0.0, 1.0).astype(np.float32)[None]


def by_polarity(single):
    """An (ON, OFF) two-channel version of a one-channel representation."""
    def split(win, p):
        return np.concatenate([single(_subset(win, win.on), p), single(_subset(win, ~win.on), p)])
    return split


REPRESENTATIONS = {
    "count": count_frame,
    "count_pol": by_polarity(count_frame),
    "ts": time_surface,
    "ts_linear": time_surface_linear,
    "ts_pol": by_polarity(time_surface),
    "voxel": voxel_grid,
}


# ---------------------------------------------------------------------------- depth in the ball box

def ball_depths(name, test, calib, rect_l, rect_r, events):
    """Depths of all matched pixels in the ball box over the test's time ranges, and compute time."""
    spec = c.TESTS[test]
    ev_l, ev_r = events
    x0, y0, x1, y1 = spec["roi"]
    params = MatchParams(cost="census", max_disp=c.MAX_DISP)
    window, step = int(c.WINDOW_MS * 1000), int(c.STEP_MS * 1000)
    first = max(ev_l.t[0], ev_r.t[0])
    depths, n_steps, seconds = [], 0, 0.0
    tic = time.time()
    for t_start, t_stop in spec["times"]:
        for t_ref in range(int(first + t_start * 1e6) + window, int(first + t_stop * 1e6) + 1, step):
            win_l = c.rectify_window(ev_l, rect_l, t_ref - window, t_ref)
            win_r = c.rectify_window(ev_r, rect_r, t_ref - window, t_ref, c.ROW_SHIFT)
            rep_l = REPRESENTATIONS[name](win_l, ReprParams())
            rep_r = REPRESENTATIONS[name](win_r, ReprParams())
            res = match(rep_l, rep_r, event_count(win_l), params, int(calib.disparity_sign))
            z = calib.depth_from_disparity(res["disparity"])[y0:y1, x0:x1]
            depths.append(z[np.isfinite(z)])
            n_steps += 1
        seconds += t_stop - t_start
    return np.concatenate(depths), n_steps, (time.time() - tic) / seconds


def summary(z, truth):
    rel = (z - truth) / truth
    return dict(points=z.size, median_m=float(np.median(z)), error_pct=100 * float(np.median(rel)),
                mae_pct=100 * float(np.mean(np.abs(rel))), within10_pct=100 * float(np.mean(np.abs(rel) <= 0.10)))


# ---------------------------------------------------------------------------- figure

def show(ax, img, title, cmap="gray_r", vmin=None, vmax=None):
    ax.imshow(img, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest")
    ax.set_title(title)
    c.no_ticks(ax)


def two_colour(on, off):
    """ON channel in red, OFF channel in blue, on white."""
    scale = max(np.percentile(np.concatenate([on.ravel(), off.ravel()]), 99.5), 1e-6)
    a, b = np.clip(on / scale, 0, 1), np.clip(off / scale, 0, 1)
    return np.stack([1 - 0.15 * a - 0.9 * b, 1 - 0.9 * a - 0.75 * b, 1 - 0.9 * a - 0.15 * b], -1).clip(0, 1)


def figure(folder, calib, rect_l, events):
    ev_l, _ = events
    window = int(c.WINDOW_MS * 1000)
    t_ref = int(ev_l.t[0] + FIGURE_T_S * 1e6)
    win = c.rectify_window(ev_l, rect_l, t_ref - window, t_ref)
    # A square crop around the ball: the middle of the events inside the ball box.
    x0, y0, x1, y1 = c.TESTS[FIGURE_TEST]["roi"]
    in_box = (win.x >= x0) & (win.x < x1) & (win.y >= y0) & (win.y < y1)
    cx, cy = int(np.median(win.x[in_box])), int(np.median(win.y[in_box]))
    half = 20
    crop = (slice(cy - half, cy + half), slice(cx - half, cx + half))

    fig = plt.figure(figsize=(9, 8))
    grid = fig.add_gridspec(3, 4, height_ratios=[1.6, 1, 1])

    # The raw events, as recorded: not rectified, no noise filter.
    raw_l, _ = c.load_pair(os.path.join(c.LAB, FIGURE_TEST), noise_filter_ms=0)
    ax = fig.add_subplot(grid[0, 1:3])
    ax.imshow(c.raw_event_image(raw_l, t_ref - window, t_ref), interpolation="nearest")
    ax.set_title(f"Raw events of the left camera, the last {c.WINDOW_MS:g} ms (red ON, blue OFF)")
    c.no_ticks(ax)

    reps = {name: f(win, ReprParams())[:, crop[0], crop[1]] for name, f in REPRESENTATIONS.items()}
    panels = [
        ("count", reps["count"][0], "gray"),
        ("count_pol (red ON, blue OFF)", two_colour(*reps["count_pol"]), None),
        ("ts (exponential, 10 ms)", reps["ts"][0], "gray"),
        ("ts_linear", reps["ts_linear"][0], "gray"),
        ("ts_pol (red ON, blue OFF)", two_colour(*reps["ts_pol"]), None),
    ] + [(f"voxel, bin {b + 1} of 3", reps["voxel"][b], "voxel") for b in range(3)]
    for k, (title, img, kind) in enumerate(panels):
        ax = fig.add_subplot(grid[1 + k // 4, k % 4])
        if kind == "voxel":
            v = max(np.percentile(np.abs(reps["voxel"]), 99.5), 1e-6)
            show(ax, img, title, cmap="RdBu_r", vmin=-v, vmax=v)
        elif kind == "gray":
            show(ax, img, title, vmin=0, vmax=max(np.percentile(img, 99.5), 1e-6))
        else:
            show(ax, img, title)
    fig.suptitle(f"{FIGURE_TEST} (ball at 2 m) at {FIGURE_T_S:g} s. Below: the six representations of the "
                 f"same window\n(noise-filtered and rectified, as depth.py uses them), cropped to {2 * half} x {2 * half} px "
                 "around the ball", y=1.0)
    fig.tight_layout()
    c.save(fig, folder, "representations")


def main():
    folder = c.out_dir("1_representations")
    calib = c.StereoCalib(c.CONFIG)
    rect_l, rect_r = c.make_rectifiers(calib)

    rows = []
    for test, spec in c.TESTS.items():
        events = c.load_pair(os.path.join(c.LAB, test))
        if test == FIGURE_TEST:
            figure(folder, calib, rect_l, events)
        for name in REPRESENTATIONS:
            z, n_steps, compute = ball_depths(name, test, calib, rect_l, rect_r, events)
            rows.append(dict(test=test, truth_m=spec["truth_m"], representation=name, steps=n_steps,
                             compute_s=compute, **summary(z, spec["truth_m"])))
            print(f"{test} {name:10s} {rows[-1]['points']:5d} points, MAE {rows[-1]['mae_pct']:.1f} %")

    c.write_table(folder, rows, [
        ("test", "Test", "{}"), ("truth_m", "Tape", "{:.0f} m"), ("representation", "Representation", "`{}`"),
        ("points", "Points", "{}"), ("median_m", "Median", "{:.3f} m"), ("error_pct", "Error of median", "{:+.1f} %"),
        ("mae_pct", "MAE", "{:.1f} %"), ("within10_pct", "Within ±10 %", "{:.1f} %"),
        ("compute_s", "Compute per s", "{:.1f} s")])
    c.write_data_used(folder, f"""
# Data used: section 1, representations

Recordings: `{c.LAB}/lab_test01`, `lab_test02`, `lab_test03` (left and right .npz).
Calibration: `{c.CONFIG}`, row shift {c.ROW_SHIFT:g} (check_rectification.py).

| Test | Tape distance | Time ranges (s from start) | Ball box (rectified left x0 y0 x1 y1) |
| --- | --- | --- | --- |
""" + "\n".join(f"| {t} | {s['truth_m']:g} m | {', '.join(f'{a}-{b}' for a, b in s['times'])} | "
                f"{' '.join(map(str, s['roi']))} |" for t, s in c.TESTS.items()) + f"""

Settings, the same for every representation: noise filter {c.NOISE_FILTER_MS:g} ms, window
{c.WINDOW_MS:g} ms every {c.STEP_MS:g} ms, census cost (7 x 7), patch 11, disparities 0-{c.MAX_DISP - 1},
left-right check, the default cost and uniqueness limits of depth.py. Every matched pixel
inside the ball box counts. Error and MAE are relative to the tape distance.
Figure: {FIGURE_TEST} at {FIGURE_T_S:g} s.
""")


if __name__ == "__main__":
    main()
