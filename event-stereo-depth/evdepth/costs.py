"""Matching costs: how different a left patch is from a right patch at each disparity.

Every cost is a function

    f(left, right, params, sign) -> (cost volume (H, W, D), disparities (D,))

where left and right are (C, H, W) representations from representation.py.
Costs are in 0..1: 0 is a perfect match, 1 is no match at all (also used
where the comparison is undefined, e.g. the patch reaches outside the right
image). They are listed in COSTS under the name used by depth.py --cost.

The right pixel compared with left pixel x at disparity d is x - sign * d.

- "zncc"    zero-mean normalised cross-correlation, cost = (1 - ZNCC) / 2.
            Compares the values in the patch up to brightness and contrast.
- "census"  census transform + Hamming distance. Each pixel gets a bit code:
            one bit per neighbour in a census_size x census_size window, set
            where that neighbour is above the window mean. The cost is the
            fraction of differing bits, averaged over the patch. Only the
            order of the values matters, not their size, so it does not care
            if one camera fires more events than the other for the same edge.

Census is the main cost; ZNCC is the standard baseline. Time coincidence
on the events themselves, windowed like these costs, was also tried and replaced by the event-by-event matcher in C++
(depth_events.py, cpp/event_match.cpp); see results/DECISIONS.md.
"""
import cv2
import numpy as np


def _box(img, k):
    """Mean over a k x k window, zero outside the image."""
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


def _inside(shape, s, k):
    """Where a k x k patch shifted by s stays inside the right image."""
    return _box(_shift_x(np.ones(shape, np.float32), s), k) > 0.999


def _as_channels(img):
    return img[None] if img.ndim == 2 else img


# ------------------------------------------------------------------- ZNCC

def zncc_cost(left, right, params, sign=1):
    """(1 - ZNCC) / 2 for every pixel and disparity.

    With several channels the patch is treated as one long vector: each channel
    has its own mean removed, then covariances and variances are summed over
    the channels. A channel with more signal therefore counts more and an empty
    one does not count at all. With one channel this is the plain ZNCC.
    """
    left, right = _as_channels(left), _as_channels(right)
    k = params.patch
    mL = [_box(c, k) for c in left]
    vL = sum(_box(c * c, k) - m * m for c, m in zip(left, mL))
    disps = np.arange(params.min_disp, params.max_disp)
    _, H, W = left.shape
    vol = np.ones((H, W, disps.size), np.float32)
    for i, d in enumerate(disps):
        s = int(sign * d)
        vR = np.zeros((H, W), np.float32)
        cov = np.zeros((H, W), np.float32)
        for cl, ml, cr in zip(left, mL, right):
            r = _shift_x(cr, s)
            mR = _box(r, k)
            vR += _box(r * r, k) - mR * mR
            cov += _box(cl * r, k) - ml * mR
        denom = np.sqrt(np.maximum(vL, 0) * np.maximum(vR, 0))
        z = np.where(denom > 1e-6, cov / np.maximum(denom, 1e-6), -1.0)
        vol[..., i] = np.where(_inside((H, W), s, k), (1 - z) / 2, 1.0)
    return vol, disps


# ----------------------------------------------------------------- census

def census_transform(img, size):
    """Bit code per pixel (uint64): one bit per pixel of the size x size window,
    set where that pixel is above the window mean."""
    assert size % 2 == 1 and size * size <= 64, "census_size must be odd and at most 7"
    r = size // 2
    H, W = img.shape
    mean = _box(img, size) + 1e-6          # + tiny value so that empty areas give 0 bits
    padded = np.pad(img, r)
    code = np.zeros((H, W), np.uint64)
    for dy in range(size):
        for dx in range(size):
            bit = padded[dy:dy + H, dx:dx + W] > mean
            code = (code << np.uint64(1)) | bit.astype(np.uint64)
    return code


def census_cost(left, right, params, sign=1):
    """Fraction of differing census bits, averaged over the patch.

    Each channel is census-transformed on its own and the bit differences of
    all channels are added up.
    """
    left, right = _as_channels(left), _as_channels(right)
    size = params.census_size
    codes_l = [census_transform(c, size) for c in left]
    codes_r = [census_transform(c, size) for c in right]
    n_bits = size * size * len(codes_l)
    disps = np.arange(params.min_disp, params.max_disp)
    _, H, W = left.shape
    vol = np.ones((H, W, disps.size), np.float32)
    for i, d in enumerate(disps):
        s = int(sign * d)
        differing = np.zeros((H, W), np.float32)
        for cl, cr in zip(codes_l, codes_r):
            differing += np.bitwise_count(cl ^ _shift_x(cr, s))
        cost = _box(differing, params.patch) / n_bits
        vol[..., i] = np.where(_inside((H, W), s, params.patch), cost, 1.0)
    return vol, disps


COSTS = {
    "zncc": zncc_cost,
    "census": census_cost,
}
