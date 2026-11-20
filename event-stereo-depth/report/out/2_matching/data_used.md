# Data used: section 2, matching methods

Recordings: `/home/selma/Documents/Project/data_collection/lab/lab_test01`, `lab_test02`, `lab_test03`; calibration `/home/selma/Documents/Project/data_collection/sessions/lab_kalibrering/config`.

| Test | Tape distance | Time ranges (s from start) | Ball box (rectified left x0 y0 x1 y1) |
| --- | --- | --- | --- |
| lab_test01 | 1 m | 3.25-4.05, 5.25-6.55 | 0 195 300 232 |
| lab_test02 | 2 m | 4.2-5.0 | 115 155 300 190 |
| lab_test03 | 3 m | 2.55-3.45 | 100 148 215 170 |

Commands: the exact command lines are in `runs/*/log.txt`. Both methods: noise filter
5 ms (default), row shift -2, disparities 0-127, depth
reported every 50 ms from the last 20 ms. Windowed: `depth.py --repr voxel
--cost census`. Event by event: `depth_events.py` with its defaults (patch 11, max age 20 ms,
max time difference 5 ms, left-right check). Every point inside the ball box counts; error and
MAE are relative to the tape distance. Compute: seconds of computing per second of recording
(windowed: one core, numpy; event by event: C++ on all 16 cores of the laptop).
