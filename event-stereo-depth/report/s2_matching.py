#!/usr/bin/env python3
"""Report section 2: two matching methods on the lab ball tests.

    python report/s2_matching.py

- Windowed (conventional, like frame cameras): every 50 ms, the last 20 ms of events
  become an image (voxel grid, the best representation of section 1), and the two
  images are block-matched along the rectified rows with the census cost (depth.py).
- Event by event (novel, suits event cameras): every left event is matched the moment
  it arrives, to the disparity where the right camera's events in the same patch fired
  at the same time (depth_events.py, C++).

Both run as the scripts do by default (noise filter 5 ms), through
tests/evaluate_lab.py's run(), with the row shift and disparity range of the lab tests.

Writes report/out/2_matching/: depth_over_time.png, example.png (what each method outputs
at one moment),
table.md / table.csv, data_used.md.
"""
import os
from types import SimpleNamespace

import numpy as np

import common as c
from common import plt
from evaluate_lab import run

METHODS = {"voxel_census": "Windowed (voxel + census)", "events": "Event by event (time matching)"}
COLOURS = {"voxel_census": "tab:orange", "events": "tab:blue"}
EXAMPLE_TEST, EXAMPLE_T_S = "lab_test02", 4.6


def ball_points(out, box):
    """Points of a run inside the ball box: (step time in s from the start, depth)."""
    d = np.load(os.path.join(out, "depth.npz"))
    x0, y0, x1, y1 = box
    inside = (d["x"] >= x0) & (d["x"] < x1) & (d["y"] >= y0) & (d["y"] < y1) & np.isfinite(d["depth_m"])
    return d["times_us"][d["frame"][inside]], d["depth_m"][inside]


def main():
    folder = c.out_dir("2_matching")
    args = SimpleNamespace(data=c.LAB, config=c.CONFIG, out=folder, rerun=False,    # runs go to <out>/runs
                           row_shift=c.ROW_SHIFT, max_disp=c.MAX_DISP)

    rows, series = [], {}
    for test, spec in c.TESTS.items():
        for method in METHODS:
            times, depths, computes = [], [], []
            for rng in spec["times"]:
                out, compute = run(method, test, rng, args)
                t, z = ball_points(out, spec["roi"])
                times.append(t)
                depths.append(z)
                computes.append(compute)
            t, z = np.concatenate(times), np.concatenate(depths)
            series[test, method] = (t, z)
            rel = (z - spec["truth_m"]) / spec["truth_m"]
            rows.append(dict(test=test, truth_m=spec["truth_m"], method=METHODS[method], points=z.size,
                             median_m=float(np.median(z)), error_pct=100 * float(np.median(rel)),
                             mae_pct=100 * float(np.mean(np.abs(rel))),
                             within10_pct=100 * float(np.mean(np.abs(rel) <= 0.10)),
                             compute_s=float(np.mean(computes))))

    c.write_table(folder, rows, [
        ("test", "Test", "{}"), ("truth_m", "Tape", "{:.0f} m"), ("method", "Method", "{}"),
        ("points", "Points", "{}"), ("median_m", "Median", "{:.3f} m"), ("error_pct", "Error of median", "{:+.1f} %"),
        ("mae_pct", "MAE", "{:.1f} %"), ("within10_pct", "Within ±10 %", "{:.1f} %"),
        ("compute_s", "Compute per s of recording", "{:.2f} s")])

    figure_depth_over_time(folder, series)
    figure_example(folder, args)
    c.write_data_used(folder, f"""
# Data used: section 2, matching methods

Recordings: `{c.LAB}/lab_test01`, `lab_test02`, `lab_test03`; calibration `{c.CONFIG}`.

| Test | Tape distance | Time ranges (s from start) | Ball box (rectified left x0 y0 x1 y1) |
| --- | --- | --- | --- |
""" + "\n".join(f"| {t} | {s['truth_m']:g} m | {', '.join(f'{a}-{b}' for a, b in s['times'])} | "
                f"{' '.join(map(str, s['roi']))} |" for t, s in c.TESTS.items()) + f"""

Commands: the exact command lines are in `runs/*/log.txt`. Both methods: noise filter
{c.NOISE_FILTER_MS:g} ms (default), row shift {c.ROW_SHIFT:g}, disparities 0-{c.MAX_DISP - 1}, depth
reported every {c.STEP_MS:g} ms from the last {c.WINDOW_MS:g} ms. Windowed: `depth.py --repr voxel
--cost census`. Event by event: `depth_events.py` with its defaults (patch 11, max age 20 ms,
max time difference 5 ms, left-right check). Every point inside the ball box counts; error and
MAE are relative to the tape distance. Compute: seconds of computing per second of recording
(windowed: one core, numpy; event by event: C++ on all 16 cores of the laptop).
""")




def figure_depth_over_time(folder, series):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2))
    for ax, (test, spec) in zip(axes, c.TESTS.items()):
        for method, label in METHODS.items():
            t, z = series[test, method]
            for k, (a, b) in enumerate(spec["times"]):        # one line per time range (roll of the ball)
                steps = np.unique(t[(t >= a * 1e6) & (t <= b * 1e6 + c.WINDOW_MS * 1000)])
                med = [np.median(z[t == s]) for s in steps]
                q1 = [np.percentile(z[t == s], 25) for s in steps]
                q3 = [np.percentile(z[t == s], 75) for s in steps]
                x = steps / 1e6              # event time, about the time from the start
                ax.fill_between(x, q1, q3, color=COLOURS[method], alpha=0.2, lw=0)
                ax.plot(x, med, ".-", color=COLOURS[method], ms=3, lw=0.8, label=label if k == 0 else None)
        ax.axhline(spec["truth_m"], color="k", lw=0.8, ls="--", label="tape")
        ax.set_ylim(spec["truth_m"] * 0.8, spec["truth_m"] * 1.2)
        ax.set_title(f"{test}: ball at {spec['truth_m']:g} m")
        ax.set_xlabel("time from the start [s]")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("depth in the ball box [m]")
    axes[0].legend(fontsize=7, loc="upper left")
    fig.suptitle("Median depth per step (line) and quartiles (band)", y=1.0)
    fig.tight_layout()
    c.save(fig, folder, "depth_over_time")


def figure_example(folder, args):
    """Matched points of both methods at one moment, coloured by depth, on the left events."""
    spec = c.TESTS[EXAMPLE_TEST]
    rng = next(r for r in spec["times"] if r[0] <= EXAMPLE_T_S <= r[1])
    calib = c.StereoCalib(c.CONFIG)
    rect_l, _ = c.make_rectifiers(calib)
    ev_l, _ = c.load_pair(os.path.join(c.LAB, EXAMPLE_TEST))
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
    for ax, (method, label) in zip(axes, METHODS.items()):
        out, _ = run(method, EXAMPLE_TEST, rng, args)
        d = np.load(os.path.join(out, "depth.npz"))
        k = int(np.argmin(np.abs(d["times_us"] - (ev_l.t[0] + EXAMPLE_T_S * 1e6))))
        t_ref = int(d["times_us"][k])
        win = c.rectify_window(ev_l, rect_l, t_ref - int(c.WINDOW_MS * 1000), t_ref)
        grey = c.event_image(win.x, win.y, win.on, win.width, win.height).mean(-1, keepdims=True)
        ax.imshow(np.repeat(0.6 + 0.4 * grey, 3, -1), interpolation="nearest")
        m = d["frame"] == k
        sc = ax.scatter(d["x"][m], d["y"][m], c=d["depth_m"][m], s=2, cmap="turbo", vmin=0.5, vmax=4, linewidths=0)
        c.draw_box(ax, spec["roi"], "g")
        ax.set_title(f"{label}\n{int(m.sum())} points")
        c.no_ticks(ax)
    fig.colorbar(sc, ax=axes, shrink=0.8, label="depth [m]")
    fig.suptitle(f"{EXAMPLE_TEST} at {EXAMPLE_T_S:g} s (ball at 2 m): every matched point of one step", y=1.0)
    c.save(fig, folder, "example")


if __name__ == "__main__":
    main()
