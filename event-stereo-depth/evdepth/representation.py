"""Turning a short window of rectified events into an image for matching.

Two representations, so they can be compared:

- "ts"    time surface: each pixel holds exp(-(t_ref - t_last) / tau), where
          t_last is the latest event at that pixel. Recent events are bright,
          older ones fade. It keeps timing information, which helps tell apart
          edges that look alike but moved past at different times.
- "count" event frame: number of events per pixel (bilinearly spread over the
          four neighbours, so sub-pixel positions from rectification are kept),
          slightly blurred.

Both also return a count image, used to decide where there is enough data to
trust a match.
"""
import cv2
import numpy as np


def _nearest(xr, yr, width, height):
    xi = np.clip(np.rint(xr).astype(np.int32), 0, width - 1)
    yi = np.clip(np.rint(yr).astype(np.int32), 0, height - 1)
    return xi, yi


def event_count(xr, yr, width, height):
    """Events per pixel, nearest pixel."""
    xi, yi = _nearest(xr, yr, width, height)
    img = np.zeros((height, width), np.float32)
    np.add.at(img, (yi, xi), 1.0)
    return img


def count_frame(xr, yr, width, height, blur_sigma=0.7):
    """Event frame with bilinear splatting."""
    x0 = np.floor(xr).astype(np.int32)
    y0 = np.floor(yr).astype(np.int32)
    fx, fy = (xr - x0).astype(np.float32), (yr - y0).astype(np.float32)
    img = np.zeros((height + 1, width + 1), np.float32)
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)),
                      (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        np.add.at(img, (y0 + dy, x0 + dx), w)
    img = img[:height, :width]
    if blur_sigma > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur_sigma)
    return img


def time_surface(xr, yr, t, t_ref, tau_us, width, height):
    """Exponential time surface at time t_ref from events with times t (sorted)."""
    xi, yi = _nearest(xr, yr, width, height)
    last = np.full((height, width), -np.inf)
    # Events are sorted in time, so a plain assignment keeps the latest per pixel.
    last[yi, xi] = t.astype(np.float64)
    return np.exp(-(t_ref - last) / float(tau_us)).astype(np.float32)


def make_image(kind, xr, yr, t, t_ref, width, height, tau_us):
    if kind == "ts":
        return time_surface(xr, yr, t, t_ref, tau_us, width, height)
    if kind == "count":
        return count_frame(xr, yr, width, height)
    raise ValueError(f"unknown representation {kind!r} (use 'ts' or 'count')")
