"""Group flips into static poses and compute one set of corners per pose.

While the rig is still, successive flips show the board at the same place, so
the detected corners agree to a fraction of a pixel. While it moves, they do
not. A "view" is a run of flips whose corners agree. Runs shorter than
MIN_FLIPS_PER_POSE are treated as motion and dropped; with the setting at 1,
every detection is kept and single-flip views are only flagged in review.
"""
import numpy as np

from . import board
from . import settings as S

SIDES = ("left", "right")


def board_shift(ref, corners):
    """How far the board as a whole moved between two sets of corners.

    An affine map is fitted from ref to corners and evaluated at the outline
    of the board. Camera motion moves all corners together and shows up as
    shift; detection noise differs from corner to corner and ends up in the
    residual instead. Returns (shift, residual rms), both in pixels.
    """
    a = np.concatenate([ref, np.ones((len(ref), 1))], axis=1)
    coef, *_ = np.linalg.lstsq(a, corners, rcond=None)
    lo, hi = ref.min(0), ref.max(0)
    box = np.array([[lo[0], lo[1], 1], [hi[0], lo[1], 1], [hi[0], hi[1], 1], [lo[0], hi[1], 1]])
    shift = float(np.linalg.norm(box @ coef - box[:, :2], axis=1).max())
    residual = float(np.sqrt(((a @ coef - corners) ** 2).sum(1).mean()))
    return shift, residual


def same_pose(ref, corners):
    """True when the two detections show the board in the same place.

    Noisy detections make the fitted shift itself uncertain, by about 0.9
    times the residual (measured with pure noise), so the limit grows with it.
    Otherwise noisy recordings would have their poses split at random.
    """
    if np.linalg.norm(corners - ref, axis=1).mean() > S.MAX_CORNER_NOISE_PX:
        return False
    shift, residual = board_shift(ref, corners)
    return shift <= S.POSE_TOL_PX + 0.9 * residual


def group_poses(times, ok, corners, period_us, max_gap=S.MAX_FLIPS_GAP):
    """Split the flip sequence into poses.

    times: (N,) flip times. ok[side]: (N,) bool. corners[side]: (N, K, 2).
    Returns a list of lists of flip indices.
    """
    poses, cur, last_t = [], [], None

    def consistent(i):
        for side in ok:
            if not ok[side][i]:
                continue
            members = [j for j in cur if ok[side][j]]
            if not members:
                continue
            if not same_pose(np.median(corners[side][members], axis=0), corners[side][i]):
                return False
        return True

    for i in range(len(times)):
        if not any(ok[side][i] for side in ok):
            continue
        if cur and (times[i] - last_t > max_gap * period_us or not consistent(i)):
            poses.append(cur)
            cur = []
        cur.append(i)
        last_t = times[i]
    if cur:
        poses.append(cur)
    return poses


def accumulate(frames):
    """Sum the signed frames of one pose.

    Successive flips have opposite sign (pattern, inverse, pattern, ...), so
    each frame is first aligned to the sign of the strongest one.
    """
    frames = [f.astype(np.int32) for f in frames]
    ref = max(frames, key=lambda f: np.abs(f).sum())
    acc = np.zeros_like(ref)
    for f in frames:
        acc += f if (f * ref).sum() >= 0 else -f
    return np.clip(acc, -127, 127).astype(np.int8)


def build_views(times, ok, corners, frames, period_us, cols=S.BOARD_COLS, rows=S.BOARD_ROWS,
                min_flips=S.MIN_FLIPS_PER_POSE):
    """Return (views, acc_frames).

    Each view is a dict with the pose's time span and, per camera, the corners,
    the number of flips they come from and their scatter between flips.
    acc_frames[side] holds the accumulated image of each view, for review.

    The rig is rigid, so a pose that is static for one camera is static for
    both. Each camera therefore accumulates all flips of the pose, including
    those where its own single-flip detection failed. Both cameras then cover
    exactly the same moments, which is what the stereo calibration needs.
    """
    views = []
    acc_frames = {side: [] for side in ok}
    for members in group_poses(times, ok, corners, period_us):
        if len(members) < min_flips:
            continue
        view = {"t_start": int(times[members[0]]), "t_end": int(times[members[-1]]),
                "flips": [int(i) for i in members]}
        accs = {}
        for side in ok:
            idx = [i for i in members if ok[side][i]]
            if not idx:
                continue
            med = np.median(corners[side][idx], axis=0)
            dev = corners[side][idx] - med
            scatter = float(np.sqrt((dev ** 2).sum(-1).mean())) if len(idx) > 1 else 0.0
            acc = accumulate([frames[side][i] for i in members])
            # Corners from the accumulated image are less noisy than those of
            # a single flip. Use them when they agree with the per-flip result.
            c, _ = board.detect(acc, cols, rows)
            if c is not None and same_pose(med, c):
                source, pts = "accumulated", c
            elif len(idx) >= min_flips:
                source, pts = "median", med
            else:
                continue
            view[side] = {"corners": pts.round(4).tolist(), "n_flips": len(members),
                          "n_detected": len(idx), "scatter_px": round(scatter, 4), "source": source}
            accs[side] = acc
        if any(side in view for side in ok):
            view["id"] = len(views)
            views.append(view)
            for side in ok:
                h, w = frames[side].shape[1:]
                acc_frames[side].append(accs.get(side, np.zeros((h, w), np.int8)))
    acc_frames = {s: np.array(v, dtype=np.int8) for s, v in acc_frames.items()}
    return views, acc_frames
