"""Stereo matching along rectified rows: from two representations to a disparity map.

1. A cost volume (H x W x disparities) from costs.py, chosen with params.cost
   (census or ZNCC). Works on any (C, H, W) representation.
2. The best (lowest-cost) disparity per pixel, refined to sub-pixel with a
   parabola through the costs around it.

The result is semi-dense: a disparity only where the left camera saw events,
and only where the match passes these checks:

- enough events in the patch (otherwise there is nothing to match),
- cost of the match below a maximum,
- uniqueness: the best disparity must beat the best one that is not a direct
  neighbour by a margin (rejects repetitive structure and reflections),
- left-right consistency: matching from the right image back to the left must
  land on the same disparity (rejects occlusions and wrong matches).

Semi-global matching (smoothing the costs across the image) was tried and
removed; see results/DECISIONS.md.
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .costs import COSTS

# Default limits per cost: (max_cost, min_margin). For ZNCC they equal a
# minimum ZNCC of 0.5 and a ZNCC margin of 0.1.
DEFAULT_LIMITS = {
    "zncc": (0.25, 0.05),
    "census": (0.35, 0.02),
}


@dataclass
class MatchParams:
    cost: str = "census"        # a name from costs.COSTS
    min_disp: int = 0
    max_disp: int = 96          # exclusive upper bound, in pixels
    patch: int = 11             # odd patch size in pixels
    census_size: int = 7        # census window, odd, at most 7
    min_events: int = 6         # events in the left patch needed to try a match
    max_cost: float = None      # None: DEFAULT_LIMITS of the cost
    min_margin: float = None    # None: DEFAULT_LIMITS of the cost
    lr_tol: float = 1.0         # left-right consistency tolerance, pixels

    def __post_init__(self):
        if self.cost not in COSTS:
            raise ValueError(f"unknown cost {self.cost!r}, use one of {', '.join(COSTS)}")
        max_cost, min_margin = DEFAULT_LIMITS[self.cost]
        if self.max_cost is None:
            self.max_cost = max_cost
        if self.min_margin is None:
            self.min_margin = min_margin


def _at(vol, idx):
    """vol[y, x, idx[y, x]] for every pixel."""
    return np.take_along_axis(vol, idx[..., None], 2)[..., 0]


def _subpixel(vol, best):
    """Parabola through the costs at best-1, best, best+1."""
    D = vol.shape[2]
    b = np.clip(best, 1, D - 2)
    c0, c1, c2 = _at(vol, b - 1), _at(vol, b), _at(vol, b + 1)
    denom = c0 - 2 * c1 + c2
    with np.errstate(divide="ignore", invalid="ignore"):
        off = np.where(np.abs(denom) > 1e-6, 0.5 * (c0 - c2) / denom, 0.0)
    off = np.clip(off, -0.5, 0.5)
    off = np.where((best >= 1) & (best <= D - 2), off, 0.0)
    return best + off


def _left_right_diff(vol, disps, best, sign):
    """How far the disparity found from the right image differs from best.

    Matching from the right image uses the same costs: right pixel xr at
    disparity d compares with left pixel xr + sign * d.
    """
    H, W, D = vol.shape
    xl = np.arange(W)[None, :, None] + sign * disps[None, None, :]
    ok = (xl >= 0) & (xl < W)
    rows = np.arange(H)[:, None, None]
    vol_r = np.where(ok, vol[rows, np.clip(xl, 0, W - 1), np.arange(D)[None, None, :]], np.inf)
    best_r = np.argmin(vol_r, axis=2)
    x_r = np.clip(np.arange(W)[None, :] - sign * disps[best], 0, W - 1)
    return np.abs(best - best_r[np.arange(H)[:, None], x_r])


def match(left, right, left_count, params, sign=1):
    """Disparity map (pixels, NaN = no match) plus per-pixel confidence."""
    vol, disps = COSTS[params.cost](left, right, params, sign)
    D = vol.shape[2]

    best = np.argmin(vol, axis=2)
    cost = _at(vol, best)

    # Uniqueness: lowest cost outside best-1 .. best+1, minus the best cost.
    near_best = np.abs(np.arange(D)[None, None, :] - best[..., None]) <= 1
    margin = np.where(near_best, np.inf, vol).min(axis=2) - _at(vol, best)

    lr_diff = _left_right_diff(vol, disps, best, sign)

    events_in_patch = cv2.boxFilter(left_count, cv2.CV_32F, (params.patch, params.patch),
                                    normalize=False, borderType=cv2.BORDER_CONSTANT)
    support = (left_count > 0) & (events_in_patch >= params.min_events)
    cheap = cost <= params.max_cost
    unique = margin >= params.min_margin
    consistent = lr_diff <= params.lr_tol
    good = support & cheap & unique & consistent

    disp = _subpixel(vol, best).astype(np.float32) + params.min_disp
    disp = np.where(good, disp, np.nan).astype(np.float32)
    return {
        "disparity": disp,                 # |x_left - x_right| in pixels, NaN where rejected
        "cost": cost,                      # cost of the chosen disparity, 0 = perfect
        "margin": margin,                  # uniqueness margin
        "support": support,                # pixels where a match was attempted
        "rejected_cost": support & ~cheap,
        "rejected_unique": support & cheap & ~unique,
        "rejected_lr": support & cheap & unique & ~consistent,
    }
