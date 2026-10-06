"""Find the moments where the screen flips the checkerboard.

A flip makes every pixel on the board fire within a few tens of milliseconds,
so it shows up as a short burst in the event rate. A burst counts as a flip
only when the rate just before and after it is much lower, which is what a
still camera looks like. Flips that happen while the camera moves are mostly
dropped here already; the pose grouping in views.py removes the rest.
"""
from dataclasses import dataclass, asdict

import numpy as np

from . import settings as S


@dataclass
class Flip:
    t: int            # time of the burst peak (us)
    t0: int           # window start (us)
    t1: int           # window end (us)
    n: int            # events inside the window
    contrast: float   # burst rate / rate around it

    def to_dict(self):
        return asdict(self)


def rate_signal(t, bin_us=S.RATE_BIN_US, smooth_ms=S.RATE_SMOOTH_MS):
    """Event rate per bin and its box-smoothed version. Returns (raw, smooth, t_start)."""
    t_start = int(t[0])
    idx = ((t - t_start) // bin_us).astype(np.int64)
    raw = np.bincount(idx).astype(np.float32)
    k = max(1, int(round(smooth_ms * 1000 / bin_us)))
    smooth = np.convolve(raw, np.ones(k, np.float32) / k, mode="same")
    return raw, smooth, t_start


def find_flips(t, period_ms=S.FLIP_PERIOD_MS, min_contrast=S.MIN_FLIP_CONTRAST,
               bin_us=S.RATE_BIN_US):
    """Return the list of flips found in the sorted timestamp array t."""
    if t.size < 1000:
        return []
    raw, s, t_start = rate_signal(t, bin_us)
    period = period_ms * 1000 / bin_us                 # in bins
    nms = int(0.6 * period)
    q0, q1 = int(0.15 * period), int(0.45 * period)    # quiet zone on each side
    max_half = int(S.MAX_HALF_WINDOW_MS * 1000 / bin_us)
    min_before = int(S.MIN_WINDOW_BEFORE_MS * 1000 / bin_us)
    min_after = int(S.MIN_WINDOW_AFTER_MS * 1000 / bin_us)

    ref = float(np.percentile(s, 98))
    if ref <= 0:
        return []
    floor = 1e-3 * ref
    order = np.argsort(s)[::-1]
    order = order[s[order] >= 0.1 * ref]
    suppressed = np.zeros(s.size, bool)
    flips = []
    for pk in order:
        if suppressed[pk]:
            continue
        suppressed[max(0, pk - nms):pk + nms + 1] = True
        if pk - q1 < 0 or pk + q1 >= s.size:
            continue
        quiet = max(np.median(s[pk - q1:pk - q0]), np.median(s[pk + q0:pk + q1]), floor)
        contrast = float(s[pk] / quiet)
        if contrast < min_contrast:
            continue
        # Grow the window until the rate is back down near the quiet level,
        # but never make it shorter than the minimum: a screen refreshes row
        # by row, so a window that is too tight loses the top or bottom of
        # the board. A generous window costs nothing while the rig is still.
        level = quiet + 0.15 * (s[pk] - quiet)
        lo, hi = max(1, pk - max_half), min(s.size - 2, pk + max_half)
        i0 = pk
        while i0 > lo and s[i0 - 1] > level:
            i0 -= 1
        i1 = pk
        while i1 < hi and s[i1 + 1] > level:
            i1 += 1
        i0 = max(lo, min(i0, pk - min_before))
        i1 = min(hi, max(i1, pk + min_after))
        t0 = t_start + i0 * bin_us
        t1 = t_start + (i1 + 1) * bin_us
        flips.append(Flip(t=int(t_start + pk * bin_us), t0=int(t0), t1=int(t1),
                          n=int(raw[i0:i1 + 1].sum()), contrast=contrast))
    flips.sort(key=lambda f: f.t)
    return flips


def match_flips(flips_l, flips_r, tol_ms=S.SYNC_TOL_MS):
    """Pair left and right flips by time.

    Returns a time-sorted list of (left_index or None, right_index or None).
    """
    tol = tol_ms * 1000
    tr = np.array([f.t for f in flips_r], dtype=np.int64)
    used = np.zeros(tr.size, bool)
    out = []
    for i, f in enumerate(flips_l):
        j = None
        if tr.size:
            k = int(np.argmin(np.abs(tr - f.t)))
            if abs(int(tr[k]) - f.t) <= tol and not used[k]:
                used[k] = True
                j = k
        out.append((f.t, i, j))
    out += [(int(tr[k]), None, k) for k in np.flatnonzero(~used)]
    out.sort(key=lambda e: e[0])
    return [(i, j) for _, i, j in out]


def estimate_offset_us(rate_left, start_left, rate_right, start_right,
                       max_lag_ms=5000, bin_us=S.RATE_BIN_US):
    """Time offset (right minus left) that best aligns the two event-rate signals.

    Takes the raw rate arrays and start times from rate_signal(). The flips
    repeat, so they cannot reveal an offset of a whole number of periods; the
    movement between poses can, and it dominates this correlation.
    """
    t_start = min(start_left, start_right)
    sl, sr = (start_left - t_start) // bin_us, (start_right - t_start) // bin_us
    n = int(max(sl + rate_left.size, sr + rate_right.size))
    a, b = np.zeros(n), np.zeros(n)
    a[sl:sl + rate_left.size] = rate_left
    b[sr:sr + rate_right.size] = rate_right
    a -= a.mean()
    b -= b.mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    xc = np.fft.irfft(np.conj(np.fft.rfft(a, size)) * np.fft.rfft(b, size), size)
    max_lag = min(int(max_lag_ms * 1000 / bin_us), n - 1)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([xc[:max_lag + 1], xc[-max_lag:]])
    return int(lags[int(np.argmax(vals))] * bin_us)
