"""Turning a short window of rectified events into an image for matching.

Every representation is a function

    f(win: EventWindow, p: ReprParams) -> np.ndarray of shape (C, H, W), float32

and is listed in REPRESENTATIONS under the name used by depth.py --repr.
Whatever comes after (the matching costs in costs.py) only sees that
(C, H, W) array, so a new representation is one function plus one line in
the table, and works with every cost.

- "count"  event frame: events per pixel, bilinearly spread over the four
           neighbours (keeps the sub-pixel positions from rectification),
           slightly blurred. The simple baseline.
- "voxel"  voxel grid: the window is cut into p.bins time bins, each event
           is spread linearly over the two nearest bins (and bilinearly in
           space), weighted +1 for ON and -1 for OFF. Keeps when events
           happened inside the window, not only where, and their polarity.
           The most accurate on the simulation and the lab tests.

Time surfaces (exponential, linear and per polarity) and event frames per
polarity were also tried and removed; see results/DECISIONS.md.
"""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class EventWindow:
    """Rectified events of one camera in [t_start, t_end)."""
    x: np.ndarray        # float, rectified sub-pixel x
    y: np.ndarray        # float, rectified sub-pixel y
    t: np.ndarray        # int64, microseconds, sorted
    on: np.ndarray       # bool, True = ON (brighter) event
    t_start: float
    t_end: float
    width: int
    height: int


@dataclass
class ReprParams:
    bins: int = 3               # time bins of the voxel grid
    blur_sigma: float = 0.7     # light blur of the count-based images, pixels


# ---------------------------------------------------------------- helpers

def _nearest(win):
    xi = np.clip(np.rint(win.x).astype(np.int32), 0, win.width - 1)
    yi = np.clip(np.rint(win.y).astype(np.int32), 0, win.height - 1)
    return xi, yi


def _subset(win, mask):
    return EventWindow(win.x[mask], win.y[mask], win.t[mask], win.on[mask],
                       win.t_start, win.t_end, win.width, win.height)


def _splat(win, weights, blur_sigma):
    """Sum of the event weights per pixel, each event spread bilinearly."""
    x0 = np.floor(win.x).astype(np.int32)
    y0 = np.floor(win.y).astype(np.int32)
    fx, fy = (win.x - x0).astype(np.float32), (win.y - y0).astype(np.float32)
    img = np.zeros((win.height + 1, win.width + 1), np.float32)
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                      (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(img, (y0 + dy, x0 + dx), w * weights)
    img = img[:win.height, :win.width]
    if blur_sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur_sigma)
    return img


# -------------------------------------------------------- representations

def count_frame(win, p):
    return _splat(win, 1.0, p.blur_sigma)[None]


def voxel_grid(win, p):
    B = p.bins
    duration = max(win.t_end - win.t_start, 1.0)
    # Event time in bin units: 0 at t_start, B - 1 at t_end.
    tb = (win.t - win.t_start) / duration * (B - 1)
    sign = np.where(win.on, 1.0, -1.0).astype(np.float32)
    vox = np.zeros((B, win.height, win.width), np.float32)
    for b in range(B):
        w_time = np.maximum(0.0, 1.0 - np.abs(tb - b)).astype(np.float32)
        near = w_time > 0
        vox[b] = _splat(_subset(win, near), sign[near] * w_time[near], p.blur_sigma)
    return vox


REPRESENTATIONS = {
    "count": count_frame,
    "voxel": voxel_grid,
}


def make_representation(name, win, params=None):
    """The (C, H, W) float32 representation called name."""
    if name not in REPRESENTATIONS:
        raise ValueError(f"unknown representation {name!r}, use one of {', '.join(REPRESENTATIONS)}")
    return REPRESENTATIONS[name](win, params or ReprParams())


def event_count(win):
    """Events per pixel (nearest pixel), used to decide where there is enough data to match."""
    xi, yi = _nearest(win)
    img = np.zeros((win.height, win.width), np.float32)
    np.add.at(img, (yi, xi), 1.0)
    return img


def to_gray(rep):
    """One displayable channel from any (C, H, W) representation: sum of |channels|."""
    return np.abs(rep).sum(axis=0)
