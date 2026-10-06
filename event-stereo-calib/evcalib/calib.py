"""Mono and stereo calibration from the reviewed views, with outlier rejection."""
import cv2
import numpy as np

from . import settings as S

_CRIT = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-7)


def object_points(cols, rows, square_w, square_h=None):
    """Board corners in board coordinates (same order as board.canonical_order)."""
    square_h = square_w if square_h is None else square_h
    obj = np.zeros((rows * cols, 3), np.float32)
    grid = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    obj[:, 0] = grid[:, 0] * square_w
    obj[:, 1] = grid[:, 1] * square_h
    return obj


def _as_cv(points):
    return [np.asarray(p, np.float32).reshape(-1, 1, 2) for p in points]


def _outlier_limit(err):
    med = float(np.median(err))
    mad = float(np.median(np.abs(err - med)))
    robust = max(med + S.OUTLIER_MADS * 1.4826 * mad, 1.5 * med)
    return min(robust, S.MAX_VIEW_RMS_PX)


def mono_flags():
    return cv2.CALIB_FIX_K3 if S.FIX_K3 else 0


def view_errors_mono(obj, points, K, D, rvecs, tvecs):
    out = []
    for p, r, t in zip(points, rvecs, tvecs):
        proj, _ = cv2.projectPoints(obj, r, t, K, D)
        d = proj.reshape(-1, 2) - np.asarray(p).reshape(-1, 2)
        out.append(np.sqrt((d ** 2).sum(1).mean()))
    return np.array(out)


def calibrate_mono(points, obj, size, reject=True, max_rounds=6):
    """Calibrate one camera.

    points: list of (K, 2) corner arrays, one per view. Returns a dict with
    K, D, rms, the per-view errors and which views were kept.
    """
    keep = list(range(len(points)))
    for _ in range(max_rounds):
        pts = _as_cv([points[i] for i in keep])
        objs = [obj] * len(pts)
        rms, K, D, rvecs, tvecs, std_int, _, _ = cv2.calibrateCameraExtended(
            objs, pts, size, None, None, flags=mono_flags(), criteria=_CRIT)
        err = view_errors_mono(obj, pts, K, D, rvecs, tvecs)
        if not reject:
            break
        bad = err > _outlier_limit(err)
        if not bad.any() or (len(keep) - int(bad.sum())) < 8:
            break
        keep = [k for k, b in zip(keep, bad) if not b]
    return {"K": K, "D": D.reshape(1, -1), "rms": float(rms), "keep": keep,
            "view_err": dict(zip(keep, err.tolist())),
            "std_fx_fy_cx_cy": std_int.ravel()[:4].tolist(), "n_in": len(points)}


def _stereo_view_errors(obj, pl, pr, KL, DL, KR, DR, R, T):
    """Per view: fit the board pose in the left camera, then see how far the
    right camera's corners are from where R, T predict them (and vice versa)."""
    out = []
    Rinv, Tinv = R.T, -R.T @ T.reshape(3, 1)
    for a, b in zip(pl, pr):
        e = []
        for src, dst, Ks, Ds, Kd, Dd, Rx, Tx in ((a, b, KL, DL, KR, DR, R, T.reshape(3, 1)),
                                                 (b, a, KR, DR, KL, DL, Rinv, Tinv)):
            ok, rv, tv = cv2.solvePnP(obj, src, Ks, Ds)
            Rb = cv2.Rodrigues(rv)[0]
            proj, _ = cv2.projectPoints(obj, cv2.Rodrigues(Rx @ Rb)[0], Rx @ tv + Tx, Kd, Dd)
            d = proj.reshape(-1, 2) - dst.reshape(-1, 2)
            e.append(np.sqrt((d ** 2).sum(1).mean()))
        out.append(float(np.mean(e)))
    return np.array(out)


def calibrate_stereo(points_l, points_r, obj, size, KL, DL, KR, DR, reject=True, max_rounds=6):
    """Rotation and translation from the left to the right camera.

    The intrinsics are held fixed at the mono results, which is the robust
    choice when each camera has more views of its own than the pair shares.
    """
    keep = list(range(len(points_l)))
    for _ in range(max_rounds):
        pl = _as_cv([points_l[i] for i in keep])
        pr = _as_cv([points_r[i] for i in keep])
        res = cv2.stereoCalibrate([obj] * len(pl), pl, pr, KL, DL, KR, DR, size,
                                  flags=cv2.CALIB_FIX_INTRINSIC, criteria=_CRIT)
        rms, R, T, E, F = res[0], res[5], res[6], res[7], res[8]
        err = _stereo_view_errors(obj, pl, pr, KL, DL, KR, DR, R, T)
        if not reject:
            break
        bad = err > _outlier_limit(err)
        if not bad.any() or (len(keep) - int(bad.sum())) < 8:
            break
        keep = [k for k, b in zip(keep, bad) if not b]
    return {"R": R, "T": T.reshape(3, 1), "E": E, "F": F, "rms": float(rms), "keep": keep,
            "view_err": dict(zip(keep, err.tolist())), "n_in": len(points_l)}


def stereo_metrics(points_l, points_r, cols, rows, square_w, square_h, size, KL, DL, KR, DR, R, T):
    """Checks that do not depend on the optimiser's own error measure.

    Rectifies the corners, measures how far apart matching corners are in y
    (should be ~0), triangulates them and compares the reconstructed square
    size with the real one.
    """
    R1, R2, P1, P2, Q, _, _ = cv2.stereoRectify(KL, DL, KR, DR, size, R, T, alpha=0)
    epi, sq_err, depth = [], [], []
    for a, b in zip(points_l, points_r):
        ra = cv2.undistortPoints(np.asarray(a, np.float64).reshape(-1, 1, 2), KL, DL, R=R1, P=P1).reshape(-1, 2)
        rb = cv2.undistortPoints(np.asarray(b, np.float64).reshape(-1, 1, 2), KR, DR, R=R2, P=P2).reshape(-1, 2)
        epi.append(np.abs(ra[:, 1] - rb[:, 1]))
        X = cv2.triangulatePoints(P1, P2, ra.T, rb.T)
        X = (X[:3] / X[3]).T.reshape(rows, cols, 3)
        sq_err.append(np.abs(np.linalg.norm(np.diff(X, axis=1), axis=2) - square_w).ravel())
        sq_err.append(np.abs(np.linalg.norm(np.diff(X, axis=0), axis=2) - square_h).ravel())
        depth.append(X[..., 2].ravel())
    epi, sq_err, depth = np.concatenate(epi), np.concatenate(sq_err), np.concatenate(depth)
    return {"epipolar_mean_px": float(epi.mean()), "epipolar_p95_px": float(np.percentile(epi, 95)),
            "square_median_err_mm": float(np.median(sq_err)), "square_mean_err_mm": float(sq_err.mean()),
            "depth_min_mm": float(depth.min()), "depth_max_mm": float(depth.max()),
            "baseline_mm": float(np.linalg.norm(T)),
            "R1": R1, "R2": R2, "P1": P1, "P2": P2, "Q": Q}


def coverage(points, size, grid=4):
    """Fraction of a grid x grid division of the image that contains corners."""
    w, h = size
    pts = np.concatenate([np.asarray(p).reshape(-1, 2) for p in points])
    gx = np.clip((pts[:, 0] / w * grid).astype(int), 0, grid - 1)
    gy = np.clip((pts[:, 1] / h * grid).astype(int), 0, grid - 1)
    hist = np.zeros((grid, grid), int)
    np.add.at(hist, (gy, gx), 1)
    return hist
