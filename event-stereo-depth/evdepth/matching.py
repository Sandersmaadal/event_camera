"""Block matching along rectified rows with zero-mean normalised cross-correlation.

For every disparity d the left image is compared with the right image shifted
by d, patch by patch. Box filters give every patch's statistics at once, so
the whole cost volume (height x width x disparities) is cheap at 320 x 320.

The result is semi-dense: a disparity only where the left camera saw events,
and only where the match passes these checks:

- enough events in the patch (otherwise there is nothing to match),
- correlation above a minimum,
- uniqueness: the best disparity must beat the best one that is not a direct
  neighbour by a margin (rejects repetitive structure and reflections),
- left-right consistency: matching from the right image back to the left must
  land on the same disparity (rejects occlusions and wrong matches).
"""
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class MatchParams:
    min_disp: int = 0
    max_disp: int = 96          # exclusive upper bound, in pixels
    patch: int = 11             # odd patch size in pixels
    min_events: int = 6         # events in the left patch needed to try a match
    min_score: float = 0.5      # minimum ZNCC of the best match
    min_margin: float = 0.1     # best ZNCC minus best non-neighbouring ZNCC
    lr_tol: float = 1.0         # left-right consistency tolerance, pixels


def _box(img, k):
    return cv2.boxFilter(img, cv2.CV_32F, (k, k), normalize=True, borderType=cv2.BORDER_CONSTANT)


def _shift_x(img, s):
    """out[:, x] = img[:, x - s], zero where that is outside the image."""
    out = np.zeros_like(img)
    w = img.shape[1]
    if s >= 0:
        out[:, s:] = img[:, :w - s] if s else img
    else:
        out[:, :w + s] = img[:, -s:]
    return out


def cost_volume(left, right, params, sign=1):
    """ZNCC for every pixel and disparity. Shape (H, W, D), -1 where undefined.

    The right pixel compared with left pixel x at disparity d is x - sign * d.
    """
    k = params.patch
    eps = 1e-6
    mL = _box(left, k)
    vL = _box(left * left, k) - mL * mL
    disps = np.arange(params.min_disp, params.max_disp)
    H, W = left.shape
    vol = np.full((H, W, disps.size), -1.0, np.float32)
    inside = np.ones((H, W), np.float32)
    for i, d in enumerate(disps):
        s = int(sign * d)
        r = _shift_x(right, s)
        mR = _box(r, k)
        vR = _box(r * r, k) - mR * mR
        cov = _box(left * r, k) - mL * mR
        denom = np.sqrt(np.maximum(vL, 0) * np.maximum(vR, 0))
        z = np.where(denom > eps, cov / np.maximum(denom, eps), -1.0)
        # Patches that reach outside the right image are not compared.
        valid = _box(_shift_x(inside, s), k) > 0.999
        vol[..., i] = np.where(valid, z, -1.0)
    return vol, disps


def _subpixel(vol, best):
    """Parabola through the scores at best-1, best, best+1."""
    D = vol.shape[2]
    b = np.clip(best, 1, D - 2)
    c0 = np.take_along_axis(vol, (b - 1)[..., None], 2)[..., 0]
    c1 = np.take_along_axis(vol, b[..., None], 2)[..., 0]
    c2 = np.take_along_axis(vol, (b + 1)[..., None], 2)[..., 0]
    denom = c0 - 2 * c1 + c2
    with np.errstate(divide="ignore", invalid="ignore"):
        off = np.where(np.abs(denom) > 1e-6, 0.5 * (c0 - c2) / denom, 0.0)
    off = np.clip(off, -0.5, 0.5)
    off = np.where((best >= 1) & (best <= D - 2), off, 0.0)
    return best + off


def match(left, right, left_count, params, sign=1):
    """Disparity map (pixels, NaN = no match) plus per-pixel confidence."""
    vol, disps = cost_volume(left, right, params, sign)
    H, W, D = vol.shape

    best = np.argmax(vol, axis=2)
    score = np.take_along_axis(vol, best[..., None], 2)[..., 0]

    # Uniqueness: best score outside best-1 .. best+1.
    idx = np.arange(D)[None, None, :]
    masked = np.where(np.abs(idx - best[..., None]) <= 1, -1.0, vol)
    margin = score - masked.max(axis=2)

    # Left-right check. Matching from the right image uses the same scores:
    # right pixel xr at disparity d compares with left pixel xr + sign * d.
    xs = np.arange(W)[None, :, None]
    xl = xs + sign * disps[None, None, :]
    ok = (xl >= 0) & (xl < W)
    rows = np.arange(H)[:, None, None]
    vol_r = np.where(ok, vol[rows, np.clip(xl, 0, W - 1), np.arange(D)[None, None, :]], -1.0)
    best_r = np.argmax(vol_r, axis=2)
    x_r = np.clip(np.arange(W)[None, :] - sign * disps[best], 0, W - 1)
    lr_diff = np.abs(best - best_r[np.arange(H)[:, None], x_r])

    events_in_patch = cv2.boxFilter(left_count, cv2.CV_32F, (params.patch, params.patch),
                                    normalize=False, borderType=cv2.BORDER_CONSTANT)
    support = (left_count > 0) & (events_in_patch >= params.min_events)
    good = (support & (score >= params.min_score) & (margin >= params.min_margin)
            & (lr_diff <= params.lr_tol))

    disp = _subpixel(vol, best).astype(np.float32) + params.min_disp
    disp = np.where(good, disp, np.nan).astype(np.float32)
    return {
        "disparity": disp,                 # |x_left - x_right| in pixels, NaN where rejected
        "score": score,                    # ZNCC of the best match
        "margin": margin,                  # uniqueness margin
        "support": support,                # pixels where a match was attempted
        "rejected_score": support & (score < params.min_score),
        "rejected_unique": support & (score >= params.min_score) & (margin < params.min_margin),
        "rejected_lr": support & (score >= params.min_score) & (margin >= params.min_margin)
                       & (lr_diff > params.lr_tol),
    }
