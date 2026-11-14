"""Stereo rectification of individual events.

Each camera gets a lookup table from raw pixel (x, y) to rectified (x, y),
built once from the calibration. Rectifying an event is then a table lookup,
and after it matching events lie on the same row in both cameras.
"""
import json
import os

import cv2
import numpy as np


class StereoCalib:
    """The calibration written by event-stereo-calib/calibrate.py."""

    def __init__(self, config_dir):
        def load(name):
            path = os.path.join(config_dir, name)
            if not os.path.exists(path):
                raise SystemExit(f"{path} not found. Run calibrate.py first, or pass --config.")
            with open(path) as f:
                return json.load(f)

        cl, cr, st = load("camera_left.json"), load("camera_right.json"), load("stereo_params.json")
        self.width, self.height = int(cl["width"]), int(cl["height"])
        self.KL, self.DL = np.array(cl["K"], float), np.array(cl["D"], float)
        self.KR, self.DR = np.array(cr["K"], float), np.array(cr["D"], float)
        self.R, self.T = np.array(st["R"], float), np.array(st["T"], float).reshape(3, 1)
        size = (self.width, self.height)
        # Recomputed rather than read, so that the rectification always matches
        # R, T and the intrinsics, whatever version of calibrate.py wrote them.
        self.R1, self.R2, self.P1, self.P2, self.Q, _, _ = cv2.stereoRectify(
            self.KL, self.DL, self.KR, self.DR, size, self.R, self.T,
            flags=cv2.CALIB_ZERO_DISPARITY, alpha=0)

    @property
    def focal_px(self):
        return float(self.P1[0, 0])

    @property
    def baseline_mm(self):
        return float(abs(self.P2[0, 3] / self.P2[0, 0]))

    @property
    def disparity_sign(self):
        """+1 when a point in front of the rig has x_left > x_right after rectification.

        This is the normal case. It is -1 when the camera called "left" is
        physically on the right, and the matcher then searches the other way.
        """
        return 1 if self.P2[0, 3] < 0 else -1

    def depth_from_disparity(self, d):
        """Metric depth in metres from a disparity in pixels (|d|, any shape)."""
        d = np.asarray(d, float)
        with np.errstate(divide="ignore", invalid="ignore"):
            z = self.focal_px * self.baseline_mm / d / 1000.0
        return np.where(d > 0, z, np.nan)

    def depth_error_per_px(self, z_m):
        """How much depth changes for one pixel of disparity error, at depth z (metres)."""
        return z_m ** 2 / (self.focal_px * self.baseline_mm / 1000.0)


class EventRectifier:
    """Lookup table from raw to rectified pixel coordinates for one camera."""

    def __init__(self, K, D, R_rect, P_rect, width, height):
        xs, ys = np.meshgrid(np.arange(width, dtype=np.float64), np.arange(height, dtype=np.float64))
        pts = np.stack([xs.ravel(), ys.ravel()], 1).reshape(-1, 1, 2)
        rect = cv2.undistortPoints(pts, K, D, R=R_rect, P=P_rect).reshape(height, width, 2)
        self.map_x = rect[..., 0].astype(np.float32)   # rectified x of raw pixel (y, x)
        self.map_y = rect[..., 1].astype(np.float32)
        self.width, self.height = width, height

    def __call__(self, x, y):
        """Rectified sub-pixel coordinates and a mask of events that land inside the image."""
        xr = self.map_x[y, x]
        yr = self.map_y[y, x]
        inside = (xr >= 0) & (xr <= self.width - 1) & (yr >= 0) & (yr <= self.height - 1)
        return xr, yr, inside


def make_rectifiers(calib):
    left = EventRectifier(calib.KL, calib.DL, calib.R1, calib.P1, calib.width, calib.height)
    right = EventRectifier(calib.KR, calib.DR, calib.R2, calib.P2, calib.width, calib.height)
    return left, right
