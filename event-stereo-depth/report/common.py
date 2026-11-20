"""Shared settings and helpers for the report scripts (report/s*_*.py).

Every section script writes to report/out/<section>/:
- figures as .png and .pdf,
- table.md and table.csv with the numbers,
- data_used.md: the recordings, time windows and settings behind them.
"""
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from depth import find_inputs, rectify_window  # noqa: E402,F401  (also puts evcalib on the path)
from evcalib.events import load_events  # noqa: E402
from evdepth.noise import background_activity  # noqa: E402
from evdepth.rectify import StereoCalib, make_rectifiers  # noqa: E402,F401

DATA = os.path.expanduser("~/Documents/Project/data_collection")
LAB = os.path.join(DATA, "lab")
CONFIG = os.path.join(DATA, "sessions", "lab_kalibrering", "config")

ROW_SHIFT = -2.0          # measured with check_rectification.py on the lab tests
NOISE_FILTER_MS = 5.0     # background activity filter (evdepth/noise.py)
STEP_MS, WINDOW_MS = 50.0, 20.0
MAX_DISP = 128            # reaches down to about 0.8 m

# Lab ball tests: distance by tape, ball box in the rectified left image (x0, y0, x1, y1),
# time ranges in seconds from the start (found by eye, see results/DECISIONS.md).
from evaluate_lab import TESTS  # noqa: E402

plt.rcParams.update({"font.size": 9, "axes.titlesize": 9, "figure.dpi": 150})


def out_dir(section):
    path = os.path.join(HERE, "out", section)
    os.makedirs(path, exist_ok=True)
    return path


def load_pair(recording, noise_filter_ms=NOISE_FILTER_MS):
    """Left and right events of a recording, noise-filtered as depth.py does by default."""
    ev_l, ev_r = (load_events(f) for f in find_inputs(recording))
    if noise_filter_ms > 0:
        ev_l = background_activity(ev_l, noise_filter_ms * 1000)
        ev_r = background_activity(ev_r, noise_filter_ms * 1000)
    return ev_l, ev_r


def event_image(x, y, on, width, height):
    """White image with ON events red and OFF events blue (later events on top)."""
    img = np.ones((height, width, 3), np.float32)
    xi = np.clip(np.rint(x).astype(int), 0, width - 1)
    yi = np.clip(np.rint(y).astype(int), 0, height - 1)
    img[yi[on], xi[on]] = (0.85, 0.1, 0.1)
    img[yi[~on], xi[~on]] = (0.1, 0.25, 0.85)
    return img


def raw_event_image(ev, t0_us, t1_us):
    """event_image of the raw (not rectified) events of one camera in [t0_us, t1_us)."""
    i0, i1 = ev.window(t0_us, t1_us)
    return event_image(ev.x[i0:i1].astype(float), ev.y[i0:i1].astype(float), ev.on[i0:i1], ev.width, ev.height)


def raw_frame(folder, name, recording, t_s, window_ms, title):
    """One moment as recorded, nothing done to it: the raw events of both cameras (not
    rectified, no noise filter) in the window_ms before t_s, and the RealSense colour and
    depth frames closest in time (depth: the raw values in metres, 0 = no depth)."""
    from evdepth.realsense import RealSense
    from realsense_ball import event_zero_system_us

    ev_l, ev_r = load_pair(recording, noise_filter_ms=0)
    t_us = int(ev_l.t[0] + t_s * 1e6)
    window = int(window_ms * 1000)
    rs = RealSense(recording + "_realsense.db3")
    zero_us, _ = event_zero_system_us(recording)
    i = int(np.argmin(np.abs(rs.depth_times_us - zero_us - t_us)))
    j = int(np.argmin(np.abs(rs.color_times_us - zero_us - t_us)))

    fig, axes = plt.subplots(1, 4, figsize=(13, 3.3), gridspec_kw=dict(width_ratios=[1, 1, 1.33, 1.78]))
    for ax, ev, side in ((axes[0], ev_l, "left"), (axes[1], ev_r, "right")):
        ax.imshow(raw_event_image(ev, t_us - window, t_us), interpolation="nearest")
        ax.set_title(f"Event camera {side}")
    axes[2].imshow(rs.color(j)[:, :, ::-1])                       # stored as BGR
    axes[2].set_title("RealSense colour")
    im = axes[3].imshow(rs.depth(i), cmap="gray")
    axes[3].set_title("RealSense depth")
    fig.colorbar(im, ax=axes[3], shrink=0.8, label="depth [m] (0 = no depth)")
    for ax in axes:
        no_ticks(ax)
    fig.suptitle(f"{title}, {t_s:g} s. Events: the last {window_ms:g} ms, red ON, blue OFF", y=1.02)
    save(fig, folder, name)


def draw_box(ax, box, color="k"):
    x0, y0, x1, y1 = box
    ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=color, lw=1))


def no_ticks(ax):
    ax.set_xticks([])
    ax.set_yticks([])


def save(fig, folder, name):
    fig.savefig(os.path.join(folder, name + ".png"), bbox_inches="tight")
    fig.savefig(os.path.join(folder, name + ".pdf"), bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.join(folder, name + ".png"))


def write_table(folder, rows, columns, name="table"):
    """rows: list of dicts; columns: list of (key, header, format)."""
    with open(os.path.join(folder, name + ".csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([key for key, _, _ in columns])
        w.writerows([[r.get(key, "") for key, _, _ in columns] for r in rows])
    lines = ["| " + " | ".join(h for _, h, _ in columns) + " |",
             "|" + " --- |" * len(columns)]
    for r in rows:
        cells = [(fmt.format(r[key]) if key in r and r[key] is not None else "") for key, _, fmt in columns]
        lines.append("| " + " | ".join(cells) + " |")
    text = "\n".join(lines) + "\n"
    with open(os.path.join(folder, name + ".md"), "w") as f:
        f.write(text)
    print(text)


def write_data_used(folder, text):
    with open(os.path.join(folder, "data_used.md"), "w") as f:
        f.write(text.strip() + "\n")
