# Method choices and why

Measurements behind the choices made while building event-stereo-depth,
saved before the code was cleaned up (2026-11-16). The methods that were
removed are only documented here. Raw numbers:
`lab_before_cleanup/results.csv` and `lab_before_cleanup/summary.md`; the
methods that were kept, run again after the clean-up (identical results for
the windowed methods, the final event matcher): `lab_after_cleanup/`.

## Test data

| Recording | Truth | Ball | Time used | Ball box (rectified left image, x0 y0 x1 y1) |
| --- | --- | --- | --- | --- |
| `lab_test01` | 1 m | rolls past right to left, twice | 3.25-4.05 s and 5.25-6.55 s | 0 195 300 232 |
| `lab_test02` | 2 m | rolls past | 4.2-5.0 s | 115 155 300 190 |
| `lab_test03` | 3 m | rolls past (a person moves in the background) | 2.55-3.45 s | 100 148 215 170 |

The boxes and times were found by eye from the event activity above the
per-pixel background (`figures/ball_search_*.png`). All points inside a box
count, so a few may not be the ball. Calibration: `lab_kalibrering`,
recorded 23 minutes before the tests. Every run uses `--row-shift -2` (see
decision 1) and a step of 50 ms with a 20 ms window.

Measures, per test and method, over the points in the ball box:

- points: matched pixels in all steps together,
- error: (median depth - truth) / truth,
- MAE: mean |depth - truth| / truth (sensitive to a few far-off points, so it
  shows outliers),
- within ±10 %: share of the points within ±10 % of the truth,
- compute: seconds of computing per second of recording on a laptop (16
  threads); below 1 is faster than real time.

## Results of all methods

| Method | 1 m: points / error / MAE / ±10 % | 2 m | 3 m | Compute |
| --- | --- | --- | --- | --- |
| `voxel` + census | 5971 / +1.1 % / 3.3 % / 99.7 % | 1534 / 0.0 % / 2.3 % / 99.2 % | 731 / -3.6 % / 3.9 % / 99.2 % | 14.4 s |
| `voxel` + ZNCC | 5271 / +1.2 % / 10.5 % / 98.0 % | 1544 / -0.2 % / 0.7 % / 99.9 % | 779 / -3.5 % / 3.9 % / 99.5 % | 20.2 s |
| `count` + census | 5011 / +1.2 % / 11.1 % / 96.9 % | 1418 / 0.0 % / 4.7 % / 99.2 % | 596 / -3.5 % / 4.7 % / 97.7 % | 11.9 s |
| `count` + ZNCC | 3393 / +1.1 % / 73.1 % / 90.6 % | 1148 / 0.0 % / 9.3 % / 94.6 % | 551 / -3.2 % / 15.5 % / 93.3 % | 13.7 s |
| `count_pol` + census | 4189 / +1.1 % / 10.4 % / 98.7 % | 1439 / 0.0 % / 6.0 % / 99.1 % | 681 / -3.6 % / 5.7 % / 97.9 % | 12.7 s |
| `count_pol` + ZNCC | 4502 / +1.1 % / 23.5 % / 95.2 % | 1424 / -0.1 % / 6.4 % / 97.7 % | 738 / -3.4 % / 5.5 % / 96.5 % | 15.6 s |
| `ts` + census | 1177 / +4.2 % / 6.5 % / 87.9 % | 242 / -1.3 % / 1.2 % / 100 % | 48 / -4.1 % / 4.0 % / 100 % | 11.6 s |
| `ts` + ZNCC | 537 / +5.1 % / 133.6 % / 57.0 % | 122 / -1.3 % / 16.3 % / 69.7 % | 78 / -3.7 % / 56.7 % / 57.7 % | 14.4 s |
| `ts_linear` + census | 1184 / +4.2 % / 6.5 % / 88.3 % | 209 / -1.2 % / 1.1 % / 100 % | 17 / -3.6 % / 3.6 % / 100 % | 11.8 s |
| `ts_linear` + ZNCC | 589 / +4.4 % / 106.3 % / 62.5 % | 138 / -1.2 % / 12.7 % / 79.0 % | 64 / -3.9 % / 66.4 % / 51.6 % | 13.9 s |
| `ts_pol` + census | 776 / +4.2 % / 3.3 % / 100 % | 116 / -1.3 % / 1.2 % / 100 % | 21 / -3.6 % / 3.6 % / 100 % | 13.3 s |
| `ts_pol` + ZNCC | 467 / +4.3 % / 102.1 % / 75.6 % | 129 / -1.3 % / 13.8 % / 76.7 % | 94 / -3.6 % / 44.1 % / 72.3 % | 16.6 s |
| `voxel` + census + SGM | 6460 / +1.1 % / 5.8 % / 99.0 % | 1560 / 0.0 % / 2.3 % / 99.2 % | 760 / -3.6 % / 5.2 % / 98.3 % | 24.8 s |
| `voxel` + ZNCC + SGM | 6400 / +1.3 % / 13.0 % / 97.9 % | 1552 / -0.2 % / 0.7 % / 99.9 % | 790 / -3.5 % / 4.0 % / 99.2 % | 28.7 s |
| `count` + census + SGM | 6393 / +1.2 % / 16.3 % / 95.7 % | 1541 / 0.0 % / 6.3 % / 98.6 % | 768 / -3.3 % / 6.5 % / 95.4 % | 23.4 s |
| `count` + ZNCC + SGM | 5768 / +1.3 % / 51.4 % / 91.3 % | 1500 / 0.0 % / 7.3 % / 95.9 % | 738 / -3.1 % / 35.2 % / 89.4 % | 25.0 s |
| time coincidence, windowed (numpy) | 2145 / +1.8 % / 21.9 % / 97.6 % | 674 / -1.1 % / 19.9 % / 95.5 % | 152 / -3.3 % / 7.1 % / 93.4 % | 15.8 s |
| events, C++, first version (no left-right check, 1 core) | 5628 / +1.7 % / 3.0 % / 99.3 % | 1439 / -1.0 % / 1.3 % / 99.7 % | 408 / -3.4 % / 4.9 % / 98.0 % | 2.5 s |
| events, C++, final (left-right check, all cores) | 4745 / +1.5 % / 2.8 % / 99.9 % | 1402 / -1.0 % / 1.0 % / 100 % | 395 / -3.4 % / 3.5 % / 99.7 % | 0.2-0.7 s |
| `voxel` + census, no row shift | 4398 / +1.7 % / 7.9 % / 98.2 % | 876 / -0.5 % / 1.8 % / 99.1 % | 102 / -1.4 % / 19.2 % / 91.2 % | 14.6 s |

Simulation (textured board at 2 m in front of a wall at 6 m, true disparity
known for every pixel; disparity errors):

| Method | Points per step | Board MAE | Board > 1 px | Wall MAE | Wall > 1 px |
| --- | --- | --- | --- | --- | --- |
| `voxel` + census | 15 200 | 0.17 px | 0.3 % | 0.36 px | 2.5 % |
| `voxel` + ZNCC | 12 000 | 0.18 px | 0.3 % | 0.48 px | 2.6 % |
| `count` + census | 15 000 | 0.25 px | 0.6 % | 0.38 px | 2.0 % |
| `count` + ZNCC | 11 600 | 0.25 px | 0.5 % | 0.51 px | 2.5 % |
| `count_pol` + ZNCC | 13 300 | 0.23 px | 0.4 % | 0.45 px | 2.5 % |
| `count_pol` + census | 14 500 | 0.24 px | 0.6 % | 0.36 px | 1.9 % |
| `ts` + ZNCC | 4 100 | 0.48 px | 2.3 % | 2.52 px | 10.5 % |
| `ts_linear` + ZNCC | 4 700 | 0.42 px | 1.8 % | 1.79 px | 7.9 % |
| `ts_pol` + ZNCC | 4 900 | 0.41 px | 2.1 % | 1.55 px | 7.5 % |
| `voxel` + census + SGM | 15 700 | 0.17 px | 0.3 % | 0.36 px | 2.9 % |
| `voxel` + ZNCC + SGM | 14 400 | 0.19 px | 0.5 % | 0.54 px | 3.9 % |
| time coincidence, windowed | 7 400 | 0.95 px | 4.6 % | 6.27 px | 20.7 % |
| events, C++ (first version) | 13 000 | 2.30 px | 10.3 % | 10.45 px | 31.7 % |

## Decisions

### 1. Check the rectification on every recording; correct the lab tests by 2 rows

`check_rectification.py` matches with the right image shifted up and down
and reports which row shift fits best. The calibration recording gives -0.05
rows (the calibration itself is good: epipolar error 0.09 px). The lab tests
give -2 rows on the moving ball, the same at every x and at 1 and 2 m, and
not caused by a time offset (±4 ms changes nothing): most likely one camera
tilted by about 0.3° in the 23 minutes between calibration and the tests
(`figures/rectification_*.png`). Checked on the simulation: 0 rows when
correct, +2.04 rows when the right camera is moved 2 rows down on purpose.

Correcting it is the largest single improvement of the project:
`voxel` + census at 3 m goes from 102 to 731 points and from 91 % to 99 %
within ±10 %; ZNCC on the 2 m ball from 523 to 1544 points. Before the
correction census looked clearly better than ZNCC on the real ball; most of
that came from census tolerating the row error better.

### 2. Representation: `voxel`, with `count` as the simple baseline

- `voxel` (3 time bins, ±1 polarity) is the most accurate on the simulation
  (board MAE 0.17-0.18 px) and has the best balance of points and accuracy
  on the lab tests.
- `count` is the simplest and fastest. It is kept as the baseline; it has
  more outliers at 1 m (with census: MAE 11 % vs 3 % for `voxel`).
- Removed: the time surfaces (`ts`, `ts_linear`, `ts_pol`). They find 5-40x
  fewer points than `voxel` + census on every lab test and are 3-5x less
  accurate on the simulation. A likely reason: a time surface keeps only the
  last event per pixel, so it holds less of the pattern to match than the
  event counts do.
- Removed: `count_pol` (count per polarity). Never better than `voxel`, which
  also uses the polarity.
- The figure `figures/representations_lab_test02_4.2s.png` shows all six on
  the same moment of `lab_test02`.

### 3. Matching cost: census, with ZNCC as the standard baseline

- Census is at least as good as ZNCC everywhere and clearly better at 1 m
  (MAE 3.3 % vs 10.5 %) and on the simulation's wall (0.36 vs 0.48 px). It is
  faster (14.4 vs 20.2 s per second of recording with `voxel`) and uses only
  integer and bit operations, which suits an embedded processor.
- ZNCC is kept because it is the standard method a report is compared with.

### 4. Semi-global matching (SGM): removed

With `voxel` SGM adds only 1-8 % points. Its MAE is worse in 8 of the 12
test/method cases, equal in 2, and better only in the 2 cases of `count` +
ZNCC, the weakest combination (for example `voxel` + census at 1 m: MAE
3.3 % -> 5.8 %). On the simulation it also adds outliers (wall 2.5 % ->
2.9 % with `voxel` + census), and it costs about 70 % more computing time.
It also needs costs for every pixel, which does not fit sparse event data or
an embedded processor.

### 5. Event-based matching: event by event in C++, not in windows

- Time coincidence in 20 ms windows (numpy) finds only a third of the points
  of `voxel` + census and has many outliers (MAE 20 % at 2 m). Removed, with
  its C++ copy `time_cpp`, which was only there to check the C++ code (it
  gave identical costs).
- Event by event in C++ (`depth_events.py`): every left event is matched
  when it arrives against the right camera's latest events. With the
  left-right check it has 99.7-100 % of its points within ±10 % on all
  three tests and the lowest MAE at 1 m (2.8 %; at 2 m 1.0 %, after `voxel` + ZNCC
  with 0.7 %), and it is the only method that is faster than real time
  (0.2-0.7 s per second of recording).
- It finds fewer points than `voxel` + census at 3 m (395 vs 731), and it
  fails on the simulation, where the texture moves slowly: a point seen at
  slightly different sub-pixel positions by the two cameras then fires
  milliseconds apart, so the time stamps no longer tell the disparities
  apart. Time matching suits fast motion.

### 6. Choices inside the C++ event matcher

Measured on the three lab tests (`cpp_variants.md`):

- Left-right check: kept. Removes 3-15 % of the points, mostly wrong ones:
  within ±10 % goes to 99.7-100 % on all tests, MAE at 3 m 4.9 % -> 3.5 %. Costs
  about 40 % more computing time.
- Several cores: kept. Identical results, 6-7x faster (16 threads).
- Sub-pixel disparity from the sub-pixel event positions, instead of a
  parabola through the costs: removed. Same accuracy on all three tests; it
  bunched fewer disparities near whole pixels at 3 m (37 % vs 55 % within
  0.1 px of a whole number) but more at 1 and 2 m (35 vs 31 %, 30 vs 22 %).
  Not better, so the simpler parabola stays.
- Faster settings (`--max-age-ms 10 --patch 7 --min-events 4`): not used.
  With all cores the defaults are already real time, and the fast settings
  have more outliers (MAE at 1 m 10.1 % vs 2.8 %).

### 7. Computing only at pixels with events (numpy): not done

Only 2 % of the pixels get matched, but 48 % have an event in their 11 x 11
patch and the left-right check needs those too. Computing only those gave
identical results and saved 20-40 %; leaving them out was 3x faster but
less accurate (simulation wall error 0.51 -> 0.89 px with ZNCC). The real
speed-up came from the event-by-event C++ instead.

### 8. RealSense as the reference for the ball distance

The RealSense D435 recorded depth (1280 x 720, 15 fps) and colour during every lab
test. `realsense_ball.py` finds the ball in each depth frame and gives the distance
to its centre; `tests/evaluate_lab.py` compares every event point with the RealSense
frame at the same moment. Results in `lab_realsense/` (`summary.md`, and the
RealSense ball track per test).

| Test (tape) | RealSense, ball centre | Spread over frames | `voxel` + census vs RealSense | Events vs RealSense |
| --- | --- | --- | --- | --- |
| 1 m | 1.019 m (roll 1: about 1.07 m, roll 2: about 1.015 m) | 1.010-1.026 m (roll 2) | -1.2 %, MAE 2.1 % | -1.3 %, MAE 1.7 % |
| 2 m | 2.058 m | 2.050-2.070 m | -3.0 %, MAE 4.6 % | -3.8 %, MAE 3.7 % |
| 3 m | 3.048 m | 3.030-3.093 m | -5.5 %, MAE 6.5 % | -5.0 %, MAE 6.2 % |

- The RealSense agrees with the tape to 2-6 cm, and shows that the two rolls of
  test 1 were at different distances (about 1.07 and 1.015 m). Per-frame RealSense
  distances are a better reference than one tape distance per test.
- Against the RealSense the event depth is short by an amount that grows with
  distance: -1.3, -3.8, -5.0 % (events), -1.2, -3.0, -5.5 % (`voxel` + census). A
  constant disparity error does exactly that (depth error = z^2 / (f B) x
  disparity error): the numbers fit a disparity that is 1.3-2.0 px too large. That
  matches a camera that turned sideways by about 0.3 deg after calibration, the
  same size as the 0.3 deg tilt behind the -2 row shift (decision 1). A
  mounting offset between the RealSense and the event cameras cannot explain it:
  that would be the same number of centimetres at every distance.
- How the ball is found: the colour image says roughly where (a ball lying on the
  floor has almost the floor's depth), and the depth image is searched nearby for
  the most uniform ball-sized disc. The search is needed because the stored
  colour-to-depth calibration is off by up to about 20 px (always to the left,
  whichever way the ball rolls, so it is not a time lag). The centre is 0.9 ball
  radii behind the measured surface (a tennis ball, radius 33.5 mm, is assumed).
- The RealSense sits on the same line as the event cameras, just to the right of
  the right camera, so both measure depth from the same plane: no offset to
  correct. Not corrected: the RealSense's own error (about 2 % at
  2 m per pixel for a D435; much smaller for the median over a ball).

### 9. Darkness (lab_test07): the event cameras keep the ball, the RealSense smears it

Ball thrown in almost full darkness; the light comes on at about 14 s.
`tests/compare_ball_tracks.py` finds the ball in the events as the densest
ball-wide group of matched events per 50 ms step, and compares it with the
RealSense track. Results in `lab_test07_dark/` (`tracks.png`), figures
`figures/test07_events_vs_realsense.jpg` and `figures/test07_matched_events.jpg`.

- The event cameras see the ball as a sharp, compact blob, even with 540 000
  noise events per second (mostly dark noise). The event matcher measures it: the
  ball is a dense group of matched events at 0.9-1.5 m, the noise only scattered
  single matches.
- The RealSense depth still works in the dark (its infrared projector lights the
  scene), but its exposure goes up to 65 ms, so a thrown ball becomes a long streak
  and its depth is an average over the smear. Its colour camera sees nothing.
- Where both found the ball (39 RealSense frames, 0-13.8 s, with the noise
  filter): events minus RealSense median +2.1 %, 90 % within ±10 % (without the
  filter: 42 frames, +1.7 %, 83 %). The tracks follow the same throws at
  2.1-2.9, 4.2-5.3 and 9.3-10.5 s; at 6.0-6.9 s only the events follow the ball.
  The RealSense also reports a ball at times without an event track (5.5-5.9,
  8.4-8.9, 11-12 s), which are not checked yet: they may be the ball, or wrong
  finds.
- Cost: without a noise filter the matcher needs 3.0 s of computing per second
  of recording in the dark (0.2-0.7 s in the light), because every noise event is
  matched too. With the 5 ms filter (decision 10) 1.3 s.
- Timing: test07 has no `_info.json`, so its time comes from the start second in
  the `.raw` header (about ±0.5 s). The tracks lining up within a frame on three
  throws suggests the error is much smaller than that.
- The RealSense's infrared projector is visible to the event cameras: a dotted
  pattern appears about once a second in the dark. Worth testing with the
  projector off, or with a filter.

### 10. Noise filter: background activity filter, 5 ms, before rectification

An event is kept when one of its 8 neighbouring pixels had an event at most 5 ms
before it (`evdepth/noise.py`, C++ in `cpp/noise_filter.cpp`, 0.3 s for 7
million events). Results in `lab_noise_filter/` (all methods with the filter; the
`*_no_filter` rows are the old defaults) and `lab_test07_dark/` (`no_filter/` for
the run without it).

It removes most events: 59-75 % in the lit lab tests (mostly the 170 000 noise
events per second), 58-65 % in the dark (left and right camera).

| | 1 m | 2 m | 3 m |
| --- | --- | --- | --- |
| Events, no filter: points, MAE vs tape, computing | 4745, 2.8 %, 0.53 s | 1402, 1.0 %, 0.67 s | 395, 3.5 %, 0.24 s |
| Events, 5 ms | 4504, 2.5 %, 0.37 s | 1268, 1.0 %, 0.38 s | 304, 3.5 %, 0.17 s |
| Events, 2 ms | 3680, 2.5 %, 0.33 s | 924, 1.0 %, 0.25 s | 100 (11 of 18 steps), 3.6 %, 0.10 s |
| `voxel` + census, no filter | 5971, 3.3 % | 1534, 2.3 % | 731, 3.9 % |
| `voxel` + census, 5 ms | 5405, 2.4 % | 1398, 0.5 % | 604, 3.3 % |
| `count` + ZNCC, no filter | 3393, 73.1 % | 1148, 9.3 % | 551, 15.5 % |
| `count` + ZNCC, 5 ms | 2912, 5.7 % | 1057, 0.6 % | 460, 5.1 % |

- 5 ms: as accurate or more accurate everywhere, for every method, at the cost of
  5-23 % of the points. The weak methods gain most, because the filter removes
  the noise their outliers came from.
- The event matcher gets 1.4-1.8x faster in the light (fewer events to match).
  In the dark (lab_test07) 2.6x: 3.0 -> 1.15-1.33 s per second of recording,
  still not real time there. The windowed matching gets only a little faster: it
  computes a cost at every pixel anyway.
- In the dark the event ball track agrees better with the RealSense: within
  ±10 % in 90 % of the paired frames instead of 83 %, with 74 instead of 81 steps
  with a ball.
- 2 ms is too strong: at 3 m only 100 points in 11 of 18 steps are left.
- On the simulation it is worse at the far wall (MAE 0.36 -> 0.52 px, more than
  1 px off 2.5 -> 3.8 %; the board stays at 0.18 px). The simulation has little
  noise and a slowly moving texture, so there the filter mostly removes real
  events. The real recordings are the ones that count, but on a clean, slow scene
  the filter can cost accuracy.
- Kept at 5 ms as the default in `depth.py` and `depth_events.py`
  (`--noise-filter-ms 0` switches it off). Not tried: other filters (polarity,
  a hot-pixel list, a larger neighbourhood).

## Open points

- All methods show the same depth error pattern against the tape: about +1 % at
  1 m, 0 % at 2 m, -3.5 % at 3 m. The RealSense comparison (decision 8) shows it
  is not the tape: against the RealSense the error grows with distance, as a
  disparity error of 1.3-2.0 px would make, most likely a small sideways turn of
  a camera after calibration. To check: estimate the disparity offset on tests 1-3
  and test the correction on other recordings, or recalibrate.
- The ball boxes were set by eye; a tracker would make the evaluation
  independent of that choice.
- The simulation has no fast-moving object, so it cannot judge the event
  matcher.
