#!/usr/bin/env python3
"""Step 2: find the checkerboard in a recorded session, offline.

    python detect.py sessions/tv01

The session folder must contain left.npz and/or right.npz (written by
record.py or convert.py). This script

  1. finds every screen flip from the event rate,
  2. builds an ON-minus-OFF image for each flip and searches it exhaustively
     for the board,
  3. keeps only the poses where the rig was still (the corners agree between
     successive flips), and
  4. writes views.json plus images for review.py.

Nothing here needs the Metavision SDK.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

from evcalib import board, flips, views
from evcalib import settings as S
from evcalib.events import load_events


def find_recording(session, side):
    for ext in (".npz", ".raw", ".hdf5"):
        p = os.path.join(session, side + ext)
        if os.path.exists(p):
            return p
    return None


def _detect_one(args):
    frame, cols, rows = args
    cv2.setNumThreads(1)
    return board.detect(frame, cols, rows)


def save_rate_plot(path, s, t_start, found, used_times, period_ms):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    x = (np.arange(s.size) * S.RATE_BIN_US) / 1e6
    fig, ax = plt.subplots(figsize=(14, 3.2))
    ax.plot(x, s, lw=0.5, color="0.35")
    ft = np.array([f.t for f in found], dtype=np.int64)
    if ft.size:
        used = np.isin(ft, list(used_times))
        peak = s[np.clip((ft - t_start) // S.RATE_BIN_US, 0, s.size - 1)]
        ax.plot((ft[~used] - t_start) / 1e6, peak[~used], "x", color="tab:red", ms=5,
                label="flip, not used (moving or no board)")
        ax.plot((ft[used] - t_start) / 1e6, peak[used], "o", color="tab:green", ms=4,
                label="flip, used in a static pose")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("events / ms")
    ax.set_title(os.path.basename(path).replace(".png", "") + f"  (flip period {period_ms} ms)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="session folder containing left.npz / right.npz")
    ap.add_argument("--period-ms", type=float, default=S.FLIP_PERIOD_MS,
                    help="time between flips, FREQ_MS in the HTML page (default %(default)s)")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="parallel detection processes")
    ap.add_argument("--right-offset-us", type=int, default=0,
                    help="added to the right camera's timestamps; only needed if the hardware sync failed")
    args = ap.parse_args()
    cols, rows = S.BOARD_COLS, S.BOARD_ROWS
    period_us = args.period_ms * 1000

    # --- 1. per camera: load events, find flips, build one image per flip ---
    # One camera at a time, so that only one recording is in memory.
    found, own_frames, rate, size = {}, {}, {}, {}
    for side in views.SIDES:
        path = find_recording(args.session, side)
        if path is None:
            continue
        ev = load_events(path)
        if len(ev) == 0:
            sys.exit(f"{path} contains no events.")
        if side == "right" and args.right_offset_us:
            ev.t = ev.t + args.right_offset_us
        found[side] = flips.find_flips(ev.t, args.period_ms)
        rate[side] = flips.rate_signal(ev.t)               # (raw, smooth, t_start)
        size[side] = (ev.width, ev.height)
        # ON minus OFF events of each flip: a two-tone checkerboard image.
        own_frames[side] = np.zeros((len(found[side]), ev.height, ev.width), np.int8)
        for k, f in enumerate(found[side]):
            own_frames[side][k] = board.signed_frame(ev, f.t0, f.t1)
        dur = (ev.t[-1] - ev.t[0]) / 1e6
        gaps = np.diff([f.t for f in found[side]]) / 1000.0
        print(f"{side:5s}: {len(ev):,} events, {dur:.1f} s, {len(found[side])} flips found "
              f"(the screen flipped ~{dur * 1000 / args.period_ms:.0f} times)")
        if gaps.size > 5:
            typical = float(np.median(gaps))
            if abs(typical - args.period_ms) > 0.2 * args.period_ms:
                print(f"       WARNING: flips are typically {typical:.0f} ms apart, but the period is set "
                      f"to {args.period_ms:.0f} ms. Pass --period-ms {typical:.0f} or fix FLIP_PERIOD_MS.")
        del ev
    if not found:
        sys.exit(f"No left.npz / right.npz found in {args.session}")
    sides = list(found)

    # --- 2. put left and right flips on one time line -----------------------
    if len(sides) == 2:
        pairs = flips.match_flips(found["left"], found["right"])
        both = [(i, j) for i, j in pairs if i is not None and j is not None]
        if both:
            d = np.array([found["right"][j].t - found["left"][i].t for i, j in both]) / 1000.0
            print(f"sync : {len(both)} flips seen by both cameras, right-left offset "
                  f"median {np.median(d):+.1f} ms (spread {np.percentile(d, 95) - np.percentile(d, 5):.1f} ms)")
        # The flips repeat, so matching flips alone cannot see an offset of a
        # whole number of periods. The overall event-rate pattern can.
        off = flips.estimate_offset_us(rate["left"][0], rate["left"][2], rate["right"][0], rate["right"][2])
        if abs(off) > S.SYNC_TOL_MS * 1000:
            print(f"WARNING: the right camera's clock is {off / 1000:+.0f} ms off the left one, so the "
                  f"hardware sync was not active.\n         Re-run with --right-offset-us {-off} to use "
                  "this recording, and check the sync cable before recording real data.")
    else:
        only = sides[0]
        pairs = [(i, None) if only == "left" else (None, i) for i in range(len(found[only]))]
    index = {"left": [p[0] for p in pairs], "right": [p[1] for p in pairs]}
    n = len(pairs)
    times = np.array([found["left"][i].t if i is not None else found["right"][j].t
                      for i, j in pairs], dtype=np.int64)

    # --- 3. frames on the common time line -----------------------------------
    frames = {}
    for side in sides:
        w, h = size[side]
        frames[side] = np.zeros((n, h, w), np.int8)
        for k, fi in enumerate(index[side]):
            if fi is not None:
                frames[side][k] = own_frames[side][fi]
    del own_frames

    # --- 4. exhaustive board search -----------------------------------------
    ok = {s: np.zeros(n, bool) for s in sides}
    corners = {s: np.full((n, rows * cols, 2), np.nan) for s in sides}
    methods = {s: [""] * n for s in sides}
    jobs = [(s, k) for s in sides for k in range(n) if index[s][k] is not None]
    t_begin = time.time()
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = pool.map(_detect_one, [(frames[s][k], cols, rows) for s, k in jobs], chunksize=2)
        for done, ((side, k), (c, method)) in enumerate(zip(jobs, results), 1):
            if c is not None:
                ok[side][k], corners[side][k], methods[side][k] = True, c, method
            if done % 10 == 0 or done == len(jobs):
                print(f"detecting boards: {done}/{len(jobs)}", end="\r", flush=True)
    print(f"\ndetection took {time.time() - t_begin:.0f} s")
    for side in sides:
        n_flips = sum(i is not None for i in index[side])
        print(f"{side:5s}: board found in {int(ok[side].sum())} of {n_flips} flips")

    # --- 5. keep only the poses where the rig was still ---------------------
    vlist, acc = views.build_views(times, ok, corners, frames, period_us, cols, rows)
    used_flips = set()
    for v in vlist:
        used_flips.update(v["flips"])
    used_times = {s: {found[s][index[s][k]].t for k in used_flips if index[s][k] is not None}
                  for s in sides}
    for side in sides:
        n_side = sum(side in v for v in vlist)
        print(f"{side:5s}: {n_side} static poses")
    if len(sides) == 2:
        n_stereo = sum("left" in v and "right" in v for v in vlist)
        print(f"stereo: {n_stereo} static poses seen by both cameras")

    # --- 6. save -------------------------------------------------------------
    meta = {"cols": cols, "rows": rows, "sides": sides, "period_ms": args.period_ms,
            "width": size[sides[0]][0], "height": size[sides[0]][1],
            "n_flips": n, "views": vlist}
    with open(os.path.join(args.session, "views.json"), "w") as f:
        json.dump(meta, f)
    np.savez_compressed(os.path.join(args.session, "views_frames.npz"),
                        **{f"acc_{s}": acc[s] for s in sides})
    np.savez_compressed(
        os.path.join(args.session, "detections.npz"), t=times,
        **{f"ok_{s}": ok[s] for s in sides}, **{f"corners_{s}": corners[s] for s in sides},
        **{f"method_{s}": np.array(methods[s]) for s in sides})
    for side in sides:
        save_rate_plot(os.path.join(args.session, f"rate_{side}.png"), rate[side][1], rate[side][2],
                       found[side], used_times[side], args.period_ms)

    n_best = max(sum(s in v for v in vlist) for s in sides)
    print(f"\nSaved {os.path.join(args.session, 'views.json')}")
    if n_best < S.MIN_VIEWS:
        print(f"Only {n_best} static poses. Look at rate_*.png: each pose should show as a run of "
              "green flips with a flat, low rate in between. Hold each pose longer and keep the rig still.")
    print(f"Next: python review.py {args.session}")


if __name__ == "__main__":
    main()
