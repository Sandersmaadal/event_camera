"""Turn the events of one flip into an image and find the checkerboard in it.

At a flip, the squares that turn white fire ON events and the squares that
turn black fire OFF events. Counting ON minus OFF per pixel therefore gives a
real two-tone checkerboard on a grey background, which is a much better input
for OpenCV than the ON-only binary image used in the live scripts.

Because this runs offline there is no time budget: several image variants,
several upscaling factors and several detectors are tried until one of them
finds the full board.
"""
import cv2
import numpy as np

from . import settings as S


def signed_frame(ev, t0, t1):
    """ON count minus OFF count per pixel for the events in [t0, t1), as int8."""
    i0, i1 = ev.window(t0, t1)
    idx = ev.y[i0:i1].astype(np.int64) * ev.width + ev.x[i0:i1]
    on = ev.on[i0:i1]
    n = ev.width * ev.height
    s = np.bincount(idx[on], minlength=n) - np.bincount(idx[~on], minlength=n)
    return np.clip(s, -127, 127).astype(np.int8).reshape(ev.height, ev.width)


def _normalised(frame):
    """Signed frame scaled to [-1, 1], with isolated noise pixels removed.

    A median filter is deliberately not used here: it rounds off the corners
    where four squares meet, which is exactly where accuracy matters.
    """
    f = frame.astype(np.float32)
    active = (f != 0).astype(np.float32)
    neighbours = cv2.boxFilter(active, -1, (3, 3), normalize=False,
                               borderType=cv2.BORDER_CONSTANT) - active
    f[neighbours < 2] = 0
    a = np.abs(f)
    nz = a[a > 0]
    scale = max(1.0, float(np.percentile(nz, 40))) if nz.size else 1.0
    return np.clip(f / scale, -1.0, 1.0)


def render(frame):
    """8-bit grey image of a signed frame (grey = no events), for display."""
    return np.clip(127.5 + 127.5 * _normalised(frame), 0, 255).astype(np.uint8)


def candidates(frame):
    """Yield (name, 8-bit image) variants of a signed frame, best first."""
    g = _normalised(frame)
    grey = np.clip(127.5 + 127.5 * g, 0, 255).astype(np.uint8)
    yield "signed", grey

    # Same image, but everything outside the board is made white, which is
    # what the detectors expect around a printed board.
    active = (np.abs(g) > 0.3).astype(np.uint8)
    region = cv2.morphologyEx(active, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    region = cv2.morphologyEx(region, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    white_bg = grey.copy()
    white_bg[region == 0] = 255
    yield "signed-white", white_bg

    # ON-only and OFF-only binary images, as in the live scripts.
    k = np.ones((3, 3), np.uint8)
    for name, mask in (("on", g > 0.3), ("off", g < -0.3)):
        im = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, k)
        yield name, cv2.bitwise_not(im)


def _upscale(img, scale, sigma):
    """Upscale and smooth. sigma is in sensor pixels.

    Smoothing matters more than it looks: the events of one flip are sparse
    and noisy, and without it the detector misses most noisy frames. It does
    not move the corners, because a corner is a saddle point and smoothing a
    saddle point symmetrically leaves it where it is.
    """
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return cv2.GaussianBlur(big, (0, 0), sigma * scale)


def _to_source(corners, scale):
    """Map corner coordinates from the upscaled image back to sensor pixels."""
    return (corners.reshape(-1, 2).astype(np.float64) + 0.5) / scale - 0.5


def canonical_order(corners, cols, rows):
    """Order corners row by row, starting at the corner that is top-left in the image.

    The detector may start at either end of the board, and a flip to the
    inverse pattern can swap which end it picks. This makes the order the same
    for every flip and for both cameras (as long as the cameras are mounted
    the same way up and are rolled less than 90 degrees to the screen).
    """
    g = corners.reshape(rows, cols, 2)
    if (g[:, -1] - g[:, 0]).mean(0)[0] < 0:          # rows should run left to right
        g = g[:, ::-1]
    row_dir = (g[:, -1] - g[:, 0]).mean(0)
    col_dir = (g[-1] - g[0]).mean(0)
    if row_dir[0] * col_dir[1] - row_dir[1] * col_dir[0] < 0:   # and then top to bottom
        g = g[::-1]
    return np.ascontiguousarray(g).reshape(-1, 2)


def plausible(corners, cols, rows, width, height):
    """Reject detections that cannot be the board (false positives)."""
    c = corners.reshape(rows, cols, 2)
    if not np.all(np.isfinite(c)):
        return False
    if c.min() < 0 or c[..., 0].max() > width - 1 or c[..., 1].max() > height - 1:
        return False
    dx = np.linalg.norm(np.diff(c, axis=1), axis=2)
    dy = np.linalg.norm(np.diff(c, axis=0), axis=2)
    spacing = min(dx.min(), dy.min())
    if spacing < S.MIN_CORNER_SPACING_PX:
        return False
    # The corners must lie on a smooth grid: compare with a homography fit.
    # Lens distortion bends the grid a little, so the limit is generous.
    ideal = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2).astype(np.float64)
    hmat, _ = cv2.findHomography(ideal, c.reshape(-1, 2), 0)
    if hmat is None:
        return False
    proj = cv2.perspectiveTransform(ideal.reshape(-1, 1, 2), hmat).reshape(-1, 2)
    resid = np.linalg.norm(proj - c.reshape(-1, 2), axis=1).max()
    return resid < 0.35 * float(np.median(np.concatenate([dx.ravel(), dy.ravel()])))


_SB_FLAGS = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY
_CLASSIC_FLAGS = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
_SUBPIX = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.01)


# (image variant, upscale factor, smoothing in sensor pixels, normalise flag).
# Ordered by measured accuracy on clean frames; the later entries rescue
# noisy frames, small boards and odd contrast.
_ATTEMPTS = (
    ("signed", 3, 1.0, False),
    ("signed", 3, 1.8, False),
    ("signed", 2, 1.5, False),
    ("signed", 4, 0.6, False),
    ("signed", 3, 1.0, True),
    ("signed-white", 3, 1.0, False),
    ("on", 3, 1.0, False),
    ("off", 3, 1.0, False),
)


def detect(frame, cols=S.BOARD_COLS, rows=S.BOARD_ROWS):
    """Find the board in a signed frame.

    Returns (corners, method): corners is an (rows*cols, 2) float array in
    sensor pixels, in canonical order, or None when nothing was found.
    """
    h, w = frame.shape
    if np.count_nonzero(frame) < 4 * cols * rows:
        return None, ""
    cands = dict(candidates(frame))
    for name, scale, sigma, normalise in _ATTEMPTS:
        flags = _SB_FLAGS | (cv2.CALIB_CB_NORMALIZE_IMAGE if normalise else 0)
        ok, c = cv2.findChessboardCornersSB(_upscale(cands[name], scale, sigma), (cols, rows), flags=flags)
        if ok:
            c = _to_source(c, scale)
            if plausible(c, cols, rows, w, h):
                return canonical_order(c, cols, rows), f"sb{'-norm' if normalise else ''}/{name}/x{scale}/s{sigma}"
    # Last resort: the classic detector plus sub-pixel refinement.
    scale = 3
    for name in ("signed-white", "on", "off"):
        big = _upscale(cands[name], scale, 1.0)
        ok, c = cv2.findChessboardCorners(big, (cols, rows), flags=_CLASSIC_FLAGS)
        if ok:
            c = cv2.cornerSubPix(big, c, (scale + 1, scale + 1), (-1, -1), _SUBPIX)
            c = _to_source(c, scale)
            if plausible(c, cols, rows, w, h):
                return canonical_order(c, cols, rows), f"classic/{name}/x{scale}"
    return None, ""
