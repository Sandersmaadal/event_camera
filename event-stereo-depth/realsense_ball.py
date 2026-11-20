#!/usr/bin/env python3
"""Find the ball in every RealSense depth frame and measure its distance.

    python realsense_ball.py ~/Documents/Project/data_collection/lab/lab_test02
    python realsense_ball.py <recording> --start-s 4.2 --duration-s 0.8 --sheet

<recording> is the prefix of <recording>_realsense.db3 (and _info.json). The ball is
found in one of two ways (--method auto picks colour when the colour image is bright
enough, else depth):

- colour: the yellow-green ball in the colour image says roughly where to look. The
  depth image is then searched around that spot (--search-px) for the disc of 0.6
  ball radii whose depth is most uniform. The search is needed because the stored
  colour-to-depth calibration is off by up to ~20 px on the lab recordings, and a
  ball lying on the floor has nearly the floor's depth, so it cannot be found from
  depth alone.
- depth: in the dark the colour image shows nothing, but the depth (active infrared)
  still works. The ball is then a blob that is
    * at least --min-gap-m closer than the background (median over the recording),
    * nearer than --max-depth-m,
    * moving: most of its pixels changed depth since the previous frame,
    * as wide as a ball at its own depth. It may be long: the long exposure in the
      dark smears a moving ball into a streak, whose depth is the RealSense's
      average over the smear, so less reliable than a sharp ball.

Writes <recording>_realsense_ball/ball.csv, one row per depth frame with a ball:
- t_s          event time (the time base of depth.py's --start-s)
- u, v         depth image pixel
- surface_m    median depth of the ball pixels
- centre_m     distance to the ball's centre along the viewing direction (surface +
               the mean depth of the visible surface behind its front)
- pixels, method, exposure_ms
- ok           0 when centre_m differs by more than --max-jump from the median of the
               5 detections around it, usually something else than the ball
With --sheet also sheet.jpg, a crop around the ball per frame.

Times: the RealSense frames carry their capture time on the system clock. With an
_info.json the clock anchor maps them to event time to a few ms. Without one
(lab_test07) the start second from the .raw header is used, good to about +-0.5 s;
correct it with --time-offset-s.
"""
import argparse
import csv
import json
import os
import re
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evdepth.realsense import RealSense  # noqa: E402

# Seconds from the .raw header date to the event clock anchor: the anchor is set
# 0.88-0.91 s after the recording start (lab_test01-06), plus half a second because
# the header date is cut to whole seconds.
HEADER_TO_ANCHOR_S = 0.9 + 0.5

# Mean depth of a sphere's visible surface behind its front point, in radii: over the
# central disc of 0.6 radii (colour method) and over the whole disc (depth method).
CENTRAL_DISC_DEPTH = 0.90
WHOLE_DISC_DEPTH = 2 / 3


def event_zero_system_us(recording):
    """System time (us) of event time 0, and how it was found."""
    info = recording + "_info.json"
    if os.path.exists(info):
        a = json.load(open(info))["event_clock_anchor"]
        return a["system_time_us"] - a["event_time_us"], "clock anchor in _info.json"
    with open(recording + "_left.raw", "rb") as f:
        header = f.read(2000).decode(errors="replace")
    m = re.search(r"% date (\d+)-(\d+)-(\d+) (\d+):(\d+):(\d+)", header)
    if not m:
        raise SystemExit(f"No {info} and no date in the .raw header: pass --time-offset-s.")
    # The header date is local time on the recording computer; this assumes the same time zone here.
    start = time.mktime(tuple(int(g) for g in m.groups()) + (0, 0, -1))
    return (start + HEADER_TO_ANCHOR_S) * 1e6, ".raw header date (about +-0.5 s)"


def background(rs, stride=3):
    """Median depth over the recording, ignoring missing depth (0 where never seen)."""
    mm = np.stack([(rs.depth(i) * 1000).astype(np.uint16) for i in range(0, len(rs.depth_rows), stride)])
    bg = np.median(np.where(mm == 0, np.uint16(65535), mm), axis=0).astype(np.float32) / 1000
    bg[bg > 60] = 0
    return bg


# ---------------------------------------------------------------------------- colour method

def colour_ball(img, min_px=30):
    """Centre (u, v) of the biggest yellow-green blob in a colour image, or None."""
    mask = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), (25, 80, 80), (45, 255, 255))
    n, _, stats, centres = cv2.connectedComponentsWithStats(mask)
    if n < 2 or stats[1:, 4].max() < min_px:
        return None
    return centres[1 + np.argmax(stats[1:, 4])]


def disc_offsets(r):
    """Pixel offsets (dy, dx) inside a disc of radius r."""
    k = int(np.ceil(r))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    inside = xx ** 2 + yy ** 2 <= r * r
    return yy[inside], xx[inside]


def most_uniform_disc(depth, u, v, r, search_x, search_y=6):
    """The disc of radius r near (u, v) whose depth varies least (IQR): dict or None."""
    dy, dx = disc_offsets(r)
    h, w = depth.shape
    best = None
    for cy in range(v - search_y, v + search_y + 1, 2):
        for cx in range(u - search_x, u + search_x + 1):
            ys, xs = cy + dy, cx + dx
            if ys.min() < 0 or xs.min() < 0 or ys.max() >= h or xs.max() >= w:
                continue
            values = depth[ys, xs]
            if np.mean(values > 0) < 0.9:          # needs depth at almost every pixel
                continue
            values = values[values > 0]
            spread = np.percentile(values, 75) - np.percentile(values, 25)
            if best is None or spread < best["spread"]:
                best = dict(spread=spread, depth=float(np.median(values)), u=cx, v=cy, pixels=values.size)
    return best


def ball_from_colour(rs, depth, uv, args):
    """Ball near the colour detection; the disc size and the mapping depend on the depth,
    so the search is repeated three times with the depth found so far."""
    z, disc = 1.5, None
    for _ in range(3):
        ud, vd = rs.color_to_depth_px(np.array([uv[0]]), np.array([uv[1]]), z)
        r = max(0.6 * rs.depth_K[0, 0] * args.ball_radius_m / z, 2.0)
        disc = most_uniform_disc(depth, int(ud[0]), int(vd[0]), r, args.search_px)
        if disc is None:
            return None
        z = disc["depth"]
    return dict(u=disc["u"], v=disc["v"], surface_m=z, centre_m=z + CENTRAL_DISC_DEPTH * args.ball_radius_m,
                pixels=disc["pixels"], method="colour")


# ---------------------------------------------------------------------------- depth method

def ball_from_depth(rs, depth, bg, prev_depth, args):
    """Moving, ball-wide blob closer than the background; the one whose width fits best."""
    near = (depth > 0) & (depth < args.max_depth_m) & (bg > 0) & (bg - depth > args.min_gap_m)
    near = cv2.morphologyEx(near.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, labels, stats, centres = cv2.connectedComponentsWithStats(near)
    candidates = []
    for k in range(1, n):
        area, w, h = stats[k, 4], stats[k, 2], stats[k, 3]
        if area < 20:
            continue
        blob = labels == k
        z = float(np.median(depth[blob]))
        diameter = 2 * rs.depth_K[0, 0] * args.ball_radius_m / z
        width, length = min(w, h), max(w, h)
        # A smeared ball is still about one ball wide; people and furniture are much wider.
        if not (0.5 * diameter <= width <= 1.6 * diameter) or length > 10 * diameter or area < 0.3 * w * h:
            continue
        # Things that stand still for a while (a person, a bag put down) are not in the
        # median background either; a thrown ball moves, so most of its pixels change depth.
        if prev_depth is not None:
            before = prev_depth[blob]
            if np.mean((before == 0) | (np.abs(before - depth[blob]) > 0.05)) < 0.5:
                continue
        candidates.append(dict(u=int(centres[k][0]), v=int(centres[k][1]), surface_m=z,
                               centre_m=z + WHOLE_DISC_DEPTH * args.ball_radius_m, pixels=int(area),
                               method="depth", misfit=abs(width / diameter - 1)))
    if not candidates:
        return None
    ball = min(candidates, key=lambda c: c["misfit"])
    del ball["misfit"]
    return ball


# ---------------------------------------------------------------------------- output

def mark_ok(rows, max_jump):
    """ok = 1 where the distance is within max_jump of the median of the 5 detections around it."""
    z = np.array([r["centre_m"] for r in rows])
    for k, r in enumerate(rows):
        around = np.median(z[max(k - 2, 0):k + 3])
        r["ok"] = int(abs(r["centre_m"] - around) <= max_jump * around)


def write_csv(path, rows):
    fields = ["t_s", "u", "v", "surface_m", "centre_m", "pixels", "method", "exposure_ms", "ok"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()})


def crop(depth, ball, t, radius_px, size=160):
    """Depth around the ball, with a circle of the ball's size."""
    vis = cv2.applyColorMap(cv2.convertScaleAbs(depth, alpha=255 / 5), cv2.COLORMAP_JET)
    u, v = ball["u"], ball["v"]
    cv2.circle(vis, (u, v), int(radius_px), (255, 255, 255), 1)
    h = size // 2
    padded = cv2.copyMakeBorder(vis, h, h, h, h, cv2.BORDER_CONSTANT)
    tile = padded[v:v + size, u:u + size].copy()
    cv2.putText(tile, f"{t:.2f}s {ball['centre_m']:.2f}m {ball['method'][0]}", (3, 12), 0, 0.4, (255, 255, 255), 1)
    return tile


def write_sheet(path, tiles, per_row=8):
    while len(tiles) % per_row:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(path, np.vstack([np.hstack(tiles[k:k + per_row]) for k in range(0, len(tiles), per_row)]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recording", help="prefix of <recording>_realsense.db3")
    ap.add_argument("--start-s", type=float, default=None, help="event time to start at")
    ap.add_argument("--duration-s", type=float, default=None)
    ap.add_argument("--time-offset-s", type=float, default=0.0, help="added to the RealSense times")
    ap.add_argument("--ball-radius-m", type=float, default=0.0335, help="tennis ball: 0.0335")
    ap.add_argument("--method", choices=["auto", "colour", "depth"], default="auto",
                    help="auto: colour if the colour image is bright enough, else depth. A ball lying on "
                         "the floor can only be found with colour")
    ap.add_argument("--search-px", type=int, default=30, help="colour method: search range in depth pixels")
    ap.add_argument("--min-gap-m", type=float, default=0.3, help="depth method: closer than the background by")
    ap.add_argument("--max-depth-m", type=float, default=4.5, help="depth method: ignore anything farther")
    ap.add_argument("--max-jump", type=float, default=0.05, help="relative difference marked as not ok")
    ap.add_argument("--sheet", action="store_true", help="also write sheet.jpg with a crop per frame")
    ap.add_argument("--out", default=None, help="output folder (default <recording>_realsense_ball)")
    args = ap.parse_args()
    rec = os.path.expanduser(args.recording)
    out = args.out or rec + "_realsense_ball"
    os.makedirs(out, exist_ok=True)

    rs = RealSense(rec + "_realsense.db3")
    zero_us, how = event_zero_system_us(rec)
    t_depth = (rs.depth_times_us - zero_us) / 1e6 + args.time_offset_s
    t_colour = (rs.color_times_us - zero_us) / 1e6 + args.time_offset_s
    print(f"{len(t_depth)} depth frames at {t_depth[0]:.2f}-{t_depth[-1]:.2f} s event time (from the {how})")
    t0 = args.start_s if args.start_s is not None else -np.inf
    t1 = t0 + args.duration_s if args.duration_s is not None else np.inf
    frames = np.where((t_depth >= t0) & (t_depth <= t1))[0]

    if args.method == "auto":
        sample = range(0, len(t_colour), max(1, len(t_colour) // 10))
        brightness = np.median([np.median(rs.color(j)) for j in sample])
        args.method = "colour" if brightness >= 40 else "depth"
        print(f"colour image median brightness {brightness:.0f} -> method '{args.method}'")
    bg = background(rs) if args.method == "depth" else None

    rows, tiles, prev_depth = [], [], None
    for i in frames:
        depth = rs.depth(i)
        if args.method == "colour":
            j = int(np.argmin(np.abs(t_colour - t_depth[i])))
            uv = colour_ball(rs.color(j)) if abs(t_colour[j] - t_depth[i]) < 0.05 else None
            ball = ball_from_colour(rs, depth, uv, args) if uv is not None else None
        else:
            ball = ball_from_depth(rs, depth, bg, prev_depth, args)
        prev_depth = depth
        if ball is None:
            continue
        rows.append(dict(t_s=round(float(t_depth[i]), 4), **ball, exposure_ms=round(rs.exposure_ms(i), 1)))
        if args.sheet:
            radius_px = rs.depth_K[0, 0] * args.ball_radius_m / ball["surface_m"]
            tiles.append(crop(depth, ball, t_depth[i], radius_px))

    mark_ok(rows, args.max_jump)
    write_csv(os.path.join(out, "ball.csv"), rows)
    if tiles:
        write_sheet(os.path.join(out, "sheet.jpg"), tiles)
    print(f"ball found in {len(rows)} of {len(frames)} frames -> {out}/ball.csv")
    z = np.array([r["centre_m"] for r in rows if r["ok"]])
    if z.size:
        print(f"{z.size} ok; centre distance: median {np.median(z):.3f} m, "
              f"quartiles {np.percentile(z, 25):.3f}-{np.percentile(z, 75):.3f} m")


if __name__ == "__main__":
    main()
