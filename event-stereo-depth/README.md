# event-stereo-depth

Depth from the stereo GenX320 rig. Every event is rectified with the
calibration from `event-stereo-calib`, then matched to the other camera in
one of two ways:

- **Windowed** (`depth.py`): a short window of events is turned into an image
  (`voxel` grid by default) and block-matched along rectified rows (census
  cost by default). Semi-dense: a depth at the pixels with events.
- **Event by event** (`depth_events.py`, C++): every left event is matched
  the moment it arrives, against the right camera's latest events, by how
  well their timestamps coincide. No windows, a depth per event, faster than
  real time.

Which methods were compared, and why these were kept, is in
[results/DECISIONS.md](results/DECISIONS.md), with all the numbers.

## Results on the lab tests

A ball at a tape-measured distance (`tests/evaluate_lab.py`, with
`--row-shift -2`, see "Checking the rectification"). Points inside the ball's
box; within ±10 % of the true distance:

| Method | 1 m | 2 m | 3 m | Computing per second of recording |
| --- | --- | --- | --- | --- |
| `depth.py` (`voxel` + census) | 5405 points, +1.2 %, 100 % | 1398 points, -0.1 %, 100 % | 604 points, -3.4 %, 100 % | about 11-13 s |
| `depth_events.py` | 4504 points, +1.5 %, 100 % | 1268 points, -1.0 %, 99.9 % | 304 points, -3.5 %, 100 % | 0.2-0.4 s |

(points, error of the median, share within ±10 %, rounded to 0.1 %; with the
default 5 ms noise filter). The error pattern is the
same for every method. Against the RealSense instead of the tape (see
"RealSense"), the event depth is short by 1.2, 3.8 and 5.2 % at 1, 2 and 3 m:
an error that grows with distance like a 1.3-2 px disparity error, most likely
a camera that turned slightly after calibration. Details and all numbers:
[results/DECISIONS.md](results/DECISIONS.md), decisions 8-10.

## Use

```bash
pip install numpy opencv-python matplotlib pybind11
cpp/build.sh                  # the C++ part (event matcher, noise filter); needs cmake and a C++17 compiler

python depth.py <recording> --config <calib session>/config [--preview] [--roi X0 Y0 X1 Y1]
python depth_events.py <recording> --config <calib session>/config
```

`<recording>` is a folder with `left.npz` and `right.npz` (or `.raw`), or a
`record_all` prefix such as `/media/master27/T7/recordings/test01` (which
finds `test01_left.raw` and `test01_right.raw`). Reading `.raw` needs the
Metavision SDK; convert to `.npz` with `event-stereo-calib/convert.py` to
work on another machine. Run `cpp/build.sh` again after every change to the
files in `cpp/`. Without the build, `depth.py` still works with
`--noise-filter-ms 0`; `depth_events.py` needs it.

Output of `depth.py` in `<recording>_depth/` (`depth_events.py`:
`<recording>_depth_events/`):

| File | Content |
| --- | --- |
| `depth.npz` | One row per matched pixel and step: `frame`, `x`, `y` (rectified left), `disparity`, `depth_m`, `cost`, `margin`; plus `times_us` per step and the settings used |
| `events.npz` | `depth_events.py` only: every left event with its own disparity, depth and status |
| `preview/*.png` | `depth.py --preview`: rectified left and right images with row lines, and the depth map (red near, blue far) |
| `roi_depth.csv` | `depth.py --roi`: median depth in the box per step |

`python depth_to_csv.py <output folder> [--roi X0 Y0 X1 Y1]` writes
`points.csv` (every matched pixel) and `per_step.csv` (median and quartiles
of the depth per step) next to `depth.npz`.

Both scripts print how many events or pixels each check rejected. That
breakdown is the first thing to look at when results are poor.

## depth.py: windowed matching

0. **Noise filter** (`evdepth/noise.py`, `--noise-filter-ms`, default 5): an event
   is kept only when one of its 8 neighbouring pixels had an event at most 5 ms
   before it. Edges of moving objects fire in neighbouring pixels close together
   in time; noise and hot pixels fire alone. Runs in C++ (`cpp/noise_filter.cpp`),
   so it needs `cpp/build.sh`; `--noise-filter-ms 0` switches it off.
1. **Rectification** (`evdepth/rectify.py`). A lookup table per camera maps
   raw pixel (x, y) to rectified sub-pixel (x, y). After it, matching events
   are on the same row in both cameras.
2. **Representation** (`evdepth/representation.py`, `--repr`), a `(C, H, W)`
   array per camera:
   - `voxel` (default): the window cut into `--bins` time bins (3), each event
     spread linearly over the two nearest bins and bilinearly in space,
     weighted +1 for ON and -1 for OFF.
   - `count`: events per pixel, bilinear splatting, light blur. The simple
     baseline.

   To add one: write `f(win, params) -> (C, H, W)` and add it to
   `REPRESENTATIONS`.
3. **Matching cost** (`evdepth/costs.py`, `--cost`), for every pixel and
   disparity, from 0 (identical patches) to 1 (no match):
   - `census` (default): each pixel gets one bit per neighbour in a 7 x 7
     window (`--census-size`), set where the neighbour is above the window
     mean; the cost is the fraction of differing bits over the patch. Only
     the order of the values counts, so it does not care if one camera fires
     more events than the other.
   - `zncc`: zero-mean normalised cross-correlation, the standard baseline.
     With several channels the patch is compared as one stacked vector.

   To add one: write `f(left, right, params, sign) -> (cost volume, disparities)`
   and add it to `COSTS`.
4. **Disparity and rejection** (`evdepth/matching.py`). The lowest-cost
   disparity with parabolic sub-pixel refinement. Kept only when the left
   patch has enough events, the cost is below `--max-cost`, the best
   disparity beats any non-neighbouring one by `--min-margin`, and matching
   back from the right image gives the same disparity.
5. **Depth**: z = f * B / d, in the rectified left camera frame, metres.

| Option | Default | Notes |
| --- | --- | --- |
| `--window-ms` | 20 | Events per estimate. Should hold a few pixels of image motion |
| `--step-ms` | 50 | Time between estimates |
| `--max-disp` | 96 | Exclusive. The nearest depth is f * B / (max-disp - 1); the startup line prints it. 128 reaches about 0.8 m on the lab rig |
| `--min-disp` | 0 | Raise it to ignore far-away background |
| `--repr`, `--bins` | voxel, 3 | |
| `--cost` | census | `census` or `zncc` |
| `--patch` | 11 | Larger is more robust, but blurs depth edges |
| `--max-cost`, `--min-margin` | census: 0.35, 0.02; zncc: 0.25, 0.05 | Cost and uniqueness limits. For ZNCC, 0.25 means a ZNCC of at least 0.5 |
| `--noise-filter-ms` | 5 | Background activity filter, 0 = off. 2 ms is too strong at 3 m |
| `--row-shift` | 0 | Row shift measured with `check_rectification.py`, corrected in the right camera. Only when the rig moved after calibration |
| `--right-offset-us` | 0 | Only for recordings without hardware sync |

The startup line also prints the depth error caused by one pixel of
disparity error at 1, 5 and 10 m. With a 320 px sensor this, not the
matcher, is often the limit at long range.

## depth_events.py: event-by-event matching in C++

The matching is in `cpp/event_match.cpp`, used from Python as
`evdepth._evmatch` through pybind11. Left and right events are processed
together in time order; each camera keeps the time of its latest event per
pixel and polarity. Both cameras' events first go through the same noise filter
as in `depth.py`. For each left event, using only events up to its time:

1. the recent left events in the `--patch` neighbourhood (at most
   `--max-age-ms` old) are compared with the right camera's latest event of
   the same polarity at the matching pixel, at every disparity: cost
   min(time difference / `--max-dt-ms`, 1), averaged. Rows within
   `--time-rows` above and below count too, because real pixels fire
   irregularly and the partner pixel often has no recent event;
2. the best disparity must be below `--max-cost` and beat the
   non-neighbouring ones by `--min-margin`;
3. left-right check: the right camera's patch at the matched position is
   matched back to the left and must land within `--lr-tol` pixels;
4. sub-pixel disparity from a parabola through the costs.

The events are cut into time chunks that run on all cores (`--threads`).
Each chunk first replays the history a match can use, so the result does not
depend on the number of threads.

| Option | Default | Notes |
| --- | --- | --- |
| `--patch` | 11 | |
| `--max-age-ms` | 20 | Older left events are ignored |
| `--max-dt-ms` | 5 | Time difference that counts as no match |
| `--time-rows` | 2 | Rows searched above and below |
| `--min-events` | 6 | Recent left events in the patch needed |
| `--max-cost`, `--min-margin` | 0.6, 0.02 | |
| `--lr-tol` | 1 | Pixels; -1 switches the left-right check off |
| `--threads` | 0 | 0 = all cores |
| `--noise-filter-ms`, `--row-shift`, `--max-disp`, `--min-disp` | as in `depth.py` | |
| `--step-ms`, `--window-ms` | 50, 20 | Only for the steps of `depth.npz` |

The work per event is (recent left events in the patch) x (disparities) x
(2 `--time-rows` + 1), so `--patch`, `--max-age-ms` and `--time-rows` set
the speed.

Time matching needs motion. On the simulation, whose texture moves slowly,
it fails (wall MAE 10 px): a point seen at slightly different sub-pixel
positions by the two cameras then fires milliseconds apart, so the
timestamps no longer tell the disparities apart. On the rolling ball it is
the most reliable method.

## Checking the rectification

```bash
python check_rectification.py <recording> --config <config>
python check_rectification.py <recording> --config <config> --start-s 4.2 --duration-s 0.8 --step-ms 50
```

Matches every pixel with events against the right image shifted up and down
by up to 4 rows (`--max-dy`) and reports which row shift fits best: the
median, a 4 x 4 map over the image, and `rectification_check.png` in
`<recording>_rectification/`. With a calibration that still fits the rig the
shifts are centred on 0. A positive shift means a point at row y in the left
image is found at row y + dy in the right image; correct it with
`--row-shift <median>`. Only horizontal structure tells the row shift, so
pixels where the best shift does not clearly win are skipped.
`--right-offset-us` tests whether a shift seen only on moving objects is a
time offset instead.

On the lab recordings the calibration recording gives -0.05 rows, but the
lab tests (recorded 23 minutes later) give -2 rows: most likely one camera
tilted by about 0.3° after calibration. All lab results use
`--row-shift -2`; without it `voxel` + census finds 7x fewer points at 3 m.
If a camera also turned sideways, the depth would be biased in a way this
check cannot see.

For new recordings: calibrate after the rig is mounted in its final place,
don't touch it between calibration and recording, and run
`check_rectification.py` on every recording.

## RealSense

The rig's RealSense D435 recorded depth and colour (`<recording>_realsense.db3`).
`evdepth/realsense.py` reads it without ROS or librealsense: depth in metres,
colour, intrinsics, the colour-to-depth transform, and capture times on the
event clock (through the clock anchor in `_info.json`).

```bash
python realsense_ball.py <recording> [--start-s 4.2 --duration-s 0.8] [--sheet]
```

Finds the ball in every depth frame and writes `<recording>_realsense_ball/ball.csv`
(time, pixel, distance to the ball's surface and centre, `ok` = consistent with the
frames around it). With light, the yellow-green ball in the colour image says
where to look and the depth image is searched nearby for the most uniform
ball-sized disc. In the dark (`--method depth`, chosen automatically when the
colour image is dark) the ball is a moving blob closer than the background, as wide
as a ball at its depth; set `--max-depth-m` to the room's range. A ball lying on
the floor can only be found with colour. Recordings without `_info.json`
(lab_test07) take their time from the `.raw` header, good to about ±0.5 s
(`--time-offset-s` corrects it).

`tests/evaluate_lab.py` compares every point with the RealSense distance at the
same moment (columns `rs_*`, `--no-realsense` to skip).

For a ball that moves around without a fixed box (lab_test07, thrown in the dark):

```bash
python depth_events.py <recording> --config <config> --row-shift -2 --max-disp 200 \
    --out <recording>_depth_events
python realsense_ball.py <recording> --max-depth-m 2
python tests/compare_ball_tracks.py <recording> --start-s 0 --duration-s 13.8
```

`compare_ball_tracks.py` finds the ball in the matched events of every step (the
densest ball-wide group) and plots both distances over time (`tracks.png`).

## Figures

```bash
python visualize_representations.py <recording> --config <config> --t-s 2.5 [--roi X0 Y0 X1 Y1]
```

Draws the `--window-ms` of events ending at `--t-s` as a space-time point
cloud and in every representation (the voxel grid one panel per bin), to
`<recording>_repr_<t>s/` (`overview.png`, `overview.pdf`, `panels/*.png`).
The figure with all six representations that were compared is in
`results/figures/`.

## Tests

On the lab recordings (ball at a known distance; boxes and times in the
script):

```bash
python tests/evaluate_lab.py --data ~/Documents/Project/data_collection/lab \
    --config ~/Documents/Project/data_collection/sessions/lab_kalibrering/config --out <folder>
```

Writes `results.csv` and `summary.md`, with the comparison against the RealSense
(see "RealSense"). Without hardware, on a simulated
scene with known depth:

```bash
python tests/simulate_scene.py sessions/sim_depth
python depth.py sessions/sim_depth --config sessions/sim_depth/config --start-s 0.05 --step-ms 25 --preview
python tests/check_depth.py sessions/sim_depth
python tests/compare_representations.py sessions/sim_depth [--tag zncc --cost zncc]
```

The simulator renders a textured board at 2 m in front of a textured wall at
6 m, both sliding sideways, through a 400 mm baseline rig with lens
distortion and a slight relative rotation, and generates events from
log-brightness changes with threshold mismatch, timestamp jitter and noise.
`check_depth.py` compares every output point with the true depth.
`compare_representations.py` runs every representation; options it does not
know are passed on to `depth.py`. It also passes with the cameras swapped
(`--baseline-mm -400`). With the defaults (`voxel` + census, 5 ms noise filter):
board MAE 0.18 px, wall MAE 0.52 px, 3.8 % of wall points more than 1 px off
(without the filter 0.17 px, 0.36 px and 2.5 %: the simulation has little noise,
so there the filter mostly removes real events).

## Not done yet

- Other noise filters (for example one that also uses polarity, or a hot-pixel
  list); the background activity filter is the only one tried.
- A fast-moving object in the simulation, to test the event matcher against
  known depth.
- Tracking the ball's depth over time (for example a Kalman filter).
- A pixel-by-pixel comparison with the RealSense, which needs the extrinsic
  calibration between the sensors: record a checkerboard with both at the next lab
  session. (The RealSense sits on the same line as the event cameras, so the ball
  comparison needs no offset.)
- Correcting the 1.3-2 px disparity error found with the RealSense (or
  recalibrating).
- Running `depth_events.py` on the Raspberry Pi.
