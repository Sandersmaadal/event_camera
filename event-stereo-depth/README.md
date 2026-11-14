# event-stereo-depth

Semi-dense depth from the stereo GenX320 rig: every event is rectified with the
calibration from `event-stereo-calib`, a short window of events is turned into
an image, and the two images are block-matched along rectified rows.

It is a baseline: simple, interpretable, and meant to be compared against
other representations and matchers later.

## Pipeline

1. **Rectification** (`evdepth/rectify.py`). A 320 x 320 lookup table per
   camera maps raw pixel (x, y) to rectified sub-pixel (x, y), built from
   `camera_*.json` and `stereo_params.json`. After it, matching events are on
   the same row in both cameras.
2. **Representation** (`evdepth/representation.py`), chosen with `--repr`:
   - `count` (default): event frame, events per pixel with bilinear splatting
     and a light blur.
   - `ts`: exponential time surface, exp(-(t - t_last) / tau).
3. **Matching** (`evdepth/matching.py`). ZNCC over a square patch for every
   disparity, using box filters, then the best disparity with parabolic
   sub-pixel refinement.
4. **Rejection** (the confidence measures). A match is kept only when the left
   patch has enough events, the ZNCC is high enough, the best disparity beats
   any non-neighbouring one by a margin (uniqueness), and matching back from
   the right image gives the same disparity (left-right check). The output
   keeps the score and margin of every point, so you can threshold later.
5. **Depth**: z = f * B / d, in the rectified left camera frame, metres.

## Use

```
pip install numpy opencv-python
python depth.py <recording> --config <calib session>/config [--preview] [--roi X0 Y0 X1 Y1]
```

`<recording>` is a folder with `left.npz` and `right.npz` (or `.raw`), or a
`record_all` prefix such as `/media/master27/T7/recordings/test01` (which
finds `test01_left.raw` and `test01_right.raw`). Reading `.raw` needs the
Metavision SDK; convert to `.npz` on the Pi first with
`event-stereo-calib/convert.py` if you process on another machine.

Output in `<recording>_depth/`:

| File | Content |
| --- | --- |
| `depth.npz` | One row per matched pixel: `frame`, `x`, `y` (rectified left), `disparity`, `depth_m`, `score`, `margin`; plus `times_us` per frame and the settings used |
| `preview/*.png` | Rectified left and right images with row lines, and the depth map (red near, blue far) |
| `roi_depth.csv` | With `--roi`: median depth in the box per step, for comparing with a tape-measured target |

The script prints how many pixels were rejected by each check. That breakdown
is the first thing to look at when results are poor.

### Main settings

| Option | Default | Notes |
| --- | --- | --- |
| `--window-ms` | 20 | Events per estimate. Should hold a few pixels of image motion. Slow or distant objects need a longer window |
| `--step-ms` | 50 | Time between estimates |
| `--max-disp` | 96 | Exclusive. The nearest depth is f * B / (max-disp - 1). With f = 170 px and B = 400 mm, 96 px is about 0.7 m |
| `--min-disp` | 0 | Raise it to ignore far-away background |
| `--patch` | 11 | Larger is more robust, but blurs depth edges |
| `--min-score`, `--min-margin` | 0.5, 0.1 | Correlation and uniqueness limits |
| `--right-offset-us` | 0 | Only for recordings without hardware sync |

The startup line prints the depth error caused by one pixel of disparity error
at 1, 5 and 10 m for your calibration. With a 320 px sensor this, not the
matcher, is often the limit at long range.

## Checking it without hardware

```
python tests/simulate_scene.py sessions/sim_depth
python depth.py sessions/sim_depth --config sessions/sim_depth/config --start-s 0.05 --step-ms 25 --preview
python tests/check_depth.py sessions/sim_depth
```

The simulator renders a textured board at 2 m in front of a textured wall at
6 m, both sliding sideways, through a 400 mm baseline rig with lens distortion
and a slight relative rotation. It generates events from log-brightness changes
with threshold mismatch, timestamp jitter and noise. `check_depth.py`
compares every output point with the true depth.

Results with the defaults:

| Surface | Disparity error, median | MAE | Outliers (> 1 px) | Depth error, median |
| --- | --- | --- | --- | --- |
| Board, 2 m | -0.02 px | 0.25 px | 0.5 % | 0.5 % |
| Wall, 6 m | +0.02 px | 0.51 px | 2.5 % | 1.6 % |

It also passes with the cameras swapped (`--baseline-mm -400`).

Observations from the simulation, worth checking on real data:

- The event frame (`count`) matched far better than the time surface (`ts`):
  with a 10 ms window, 57 % vs 21 % of the candidate pixels were kept, and the
  board outliers were 3 % vs 12 %. The time surface depends on exact event
  timing, which differs between two pixels with different thresholds.
- The window length matters most. When the texture moved under one pixel per
  window, almost nothing matched. Going from 10 to 20 ms cut the wall outliers
  from 9 % to 2.5 %.
- Most remaining outliers are next to the board's edges, where part of the
  wall is hidden from one camera.

## Not done yet

- Temporal filtering of depth across steps.
- Voxel-grid and polarity-split representations.
- Evaluation against RealSense or lidar (needs the extrinsic calibration
  between the sensors).
- Speed: about 0.4 s per step in Python on a laptop. Fine for offline
  evaluation, not for real time.
