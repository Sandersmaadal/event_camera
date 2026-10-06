# event-stereo-calib

Intrinsic and extrinsic calibration for a stereo pair of Prophesee GenX320
event cameras, using a flickering checkerboard on a screen.

The cameras are recorded first and everything else happens afterwards, offline:

1. `record.py` records both cameras (on the Pi).
2. `detect.py` finds every screen flip in the recording, searches each one
   exhaustively for the board and keeps only the poses where the rig was still.
3. `review.py` shows each pose so you can accept or reject it with a key.
4. `calibrate.py` calibrates both cameras and the pair, and reports how good
   the result is.

The output files have the layout that the depth, rectification and tracking
scripts in `yug3nn/Master_thesis_project` read.

## Why offline

- A flip is found from the event rate, so the image is built from exactly the
  events of that flip. A live loop cuts the stream into fixed slices and often
  splits a flip in two.
- The image is ON minus OFF events, which is a real two-tone checkerboard. The
  live scripts use ON events only.
- Detections made while the camera moves are removed: a pose only counts when
  the corners agree between successive flips (`MIN_FLIPS_PER_POSE`, now 1,
  so a single detection also counts; single-flip poses are flagged in review).
- There is no time budget, so the full detector runs on an upscaled image, with
  fallbacks.
- A recording can be processed again whenever a setting changes.

## Install

```
pip install numpy opencv-python matplotlib
```

Only `record.py` and `convert.py` need the Metavision SDK, so steps 2 to 4 can
run on the Pi or on any other computer. Copy the session folder across (the
`.npz` files are enough, the `.raw` files can stay on the Pi).

## Before recording

1. Edit `evcalib/settings.py`: camera serials (`metavision_platform_info`),
   and `FLIP_PERIOD_MS` if you change `FREQ_MS` in the HTML page (400 now).
2. Screen setup. This matters more on a TV than on a laptop:
   - Backlight at maximum. A dimmed backlight usually flickers, and the
     cameras see that as a constant stream of events on the white squares.
   - Turn off motion smoothing, dynamic contrast, local dimming and eco mode.
   - Picture size 1:1 ("Just scan", "Screen fit" or similar), browser zoom
     100 %, page in full screen.
   - No lamp or window reflected in the screen.
3. Measure the board on the screen with a ruler: total width of the 10 squares
   divided by 10, and total height of the 7 squares divided by 7. The two
   numbers should agree. This value sets the scale of the stereo baseline and
   therefore of every depth you compute, and it is different for every screen.

## Workflow

```
python record.py sessions/tv01                       # on the Pi
python detect.py sessions/tv01
python review.py sessions/tv01
python calibrate.py sessions/tv01 --square-mm 68.5 --out ~/Master_thesis_project/config
```

`--square-mm` takes one value, or width and height. You can also set
`SQUARE_W_MM` in the settings. `--out` copies the three JSON files to another
folder; without it they stay in `sessions/tv01/config`.

To use recordings made with another tool (for example yug3nn's
`record_stereo.py`), put them in a folder as `left.raw` and `right.raw` and run
`python convert.py <folder>`.

### How to move the rig

Only the periods where the rig is still are used.

- Put the rig down or brace it against something, keep it **still for 2 to 3
  seconds**, then move to the next pose. At a flip every 400 ms that gives 5 to
  7 flips per pose; one is enough with `MIN_FLIPS_PER_POSE = 1`. Hand-held is usually not still enough.
- Aim for 40 to 60 poses. Expect some to be dropped.
- The whole board must be visible, in both cameras for the stereo part.
- Vary the pose: board in every part of the image including the corners and
  edges, tilted up to about 30 degrees in each direction, near and far.
- Include the distances you will measure depth at later.

With `MIN_FLIPS_PER_POSE = 1`, a flip that happens while you move can still be
kept as a pose. Check the poses flagged "few flips" in review and reject smeared ones.
Setting `FREQ_MS = 200` in the HTML page (and `FLIP_PERIOD_MS = 200`) halves
the time you need to hold each pose.

### Review keys

`a` or space accept, `r` reject, `1` reject the left image only, `2` reject the
right image only, `b` back, `f` next flagged pose, `q` save and quit. Each of
the first four moves on to the next pose. Click the window first.

Look for gross failures: a grid that does not sit on the board, corners on the
TV frame, a smeared image, or corner 0 (red circle) at different ends of the
board in the two cameras. Small errors are not visible by eye, which is what the
numbers under each image are for. `python review.py <session> --flagged` shows
only the poses where those numbers are suspicious. Poses you do not look at
count as accepted.

## Reading the result

`calibrate.py` prints a report and saves it as `config/report.txt`.

| Number | Good | What to do if it is not |
| --- | --- | --- |
| Views used per camera | 25 or more | Record more poses |
| RMS reprojection | below about 0.3 px | Reject the worst poses, check focus |
| Image coverage | 14 of 16 cells or more | Add poses near the image edges (`coverage_*.png`) |
| Baseline | within about 1 mm of a ruler measurement | Check the square size |
| Epipolar error | mean below about 0.3 px | Do not use this calibration for depth |
| Square size error | around 1 to 3 mm at 1 m | See the note on depth precision below |

The baseline is the best single check: measure the distance between the two
lens centres with a ruler and compare.

**Depth precision of this rig.** Depth error is roughly
`z^2 / (f * B) * disparity error`. With f = 170 px and a 100 mm baseline, one
pixel of disparity error is about 60 mm at 1 m and about 240 mm at 2 m. A good
calibration keeps the systematic part of the disparity error small, but it
cannot make a 320 x 320 sensor resolve depth finer than that.

## If something looks wrong

Open `sessions/<name>/rate_left.png`. Each pose should appear as a run of green
dots (flips used) with a flat, low rate in between.

- **Few flips found, or the rate between flips is high while the rig is
  still:** the screen flickers. Raise the backlight to maximum, or raise
  `BIAS_INCREMENT`.
- **Flips found but few static poses:** the rig moved during the holds. Hold
  longer and rest the rig on something. `POSE_TOL_PX` sets how much the corners
  may move between flips of one pose.
- **Board found in few flips:** the board is too small in the image (move
  closer), partly outside the image, or out of focus. Corners need to be at
  least 3 px apart.
- **Board cut off at the top or bottom in the review images:** the flip takes
  longer than the window. Raise `MIN_WINDOW_AFTER_MS`.
- **"hardware sync was not active" warning:** the two recordings do not share
  a clock. The suggested `--right-offset-us` makes this recording usable for
  calibration, but fix the sync before recording real data.

## Files in a session

| File | Written by | Content |
| --- | --- | --- |
| `left.raw`, `right.raw` | `record.py` | Native recordings |
| `left.npz`, `right.npz` | `record.py`, `convert.py` | Events as arrays `x, y, p, t` |
| `views.json` | `detect.py` | The static poses and their corners |
| `views_frames.npz` | `detect.py` | The image of each pose, for review |
| `detections.npz` | `detect.py` | Per-flip results, for debugging |
| `rate_left.png`, `rate_right.png` | `detect.py` | Event rate with the flips marked |
| `review.json` | `review.py` | Your accept/reject decisions |
| `config/camera_left.json`, `camera_right.json` | `calibrate.py` | K (3x3), D (1x5), RMS |
| `config/stereo_params.json` | `calibrate.py` | R, T (mm), E, F, rectification, checks |
| `config/report.txt`, `coverage_*.png` | `calibrate.py` | Report and corner coverage |

## Try it without hardware

```
python tests/simulate.py sessions/sim          # a few minutes
python detect.py sessions/sim
python review.py sessions/sim
python calibrate.py sessions/sim --square-mm 70
python tests/check_truth.py sessions/sim
```

`simulate.py` generates the events a stereo rig would produce in front of a
flickering board, including the movement between poses, and stores the true
calibration. `check_truth.py` compares the result with it.

## What has been tested

Steps 2 to 4 were run end to end on simulated stereo recordings with a known
calibration (30 poses, 320 x 320, about 95 mm baseline, flips during movement
included):

| Recording | Focal length error | Baseline error | Rotation error |
| --- | --- | --- | --- |
| Clean | below 0.5 px | 0.2 mm | 0.09 deg |
| 40 % of events removed, noise events added at 3x the signal | below 0.9 px | 0.3 mm | 0.05 deg |

In both, every flip that happened during movement was kept out of the poses or
had no measurable effect on them.

`record.py` and `convert.py` use the same Metavision calls as yug3nn's
`camera_streamer.py` and were run against a stand-in for the SDK, but not on
real cameras. The pipeline has not been run on a real TV recording yet, so
expect to adjust a setting or two on the first one.
