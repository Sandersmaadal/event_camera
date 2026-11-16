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

## Open points

- All methods show the same depth error pattern: about +1 % at 1 m, 0 % at
  2 m, -3.5 % at 3 m. Because it is the same for every method it comes from
  the setup, not the matching: how the distance was measured (from which
  point of the rig, to the front or the centre of the ball) and how exactly
  the ball was placed. At 3 m, 3.5 % is about 10 cm. It could also be a
  small sideways turn of a camera after calibration, which the rectification
  check cannot see.
- The ball boxes were set by eye; a tracker would make the evaluation
  independent of that choice.
- The simulation has no fast-moving object, so it cannot judge the event
  matcher.
