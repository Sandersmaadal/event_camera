# Data used: section 1, representations

Recordings: `/home/selma/Documents/Project/data_collection/lab/lab_test01`, `lab_test02`, `lab_test03` (left and right .npz).
Calibration: `/home/selma/Documents/Project/data_collection/sessions/lab_kalibrering/config`, row shift -2 (check_rectification.py).

| Test | Tape distance | Time ranges (s from start) | Ball box (rectified left x0 y0 x1 y1) |
| --- | --- | --- | --- |
| lab_test01 | 1 m | 3.25-4.05, 5.25-6.55 | 0 195 300 232 |
| lab_test02 | 2 m | 4.2-5.0 | 115 155 300 190 |
| lab_test03 | 3 m | 2.55-3.45 | 100 148 215 170 |

Settings, the same for every representation: noise filter 5 ms, window
20 ms every 50 ms, census cost (7 x 7), patch 11, disparities 0-127,
left-right check, the default cost and uniqueness limits of depth.py. Every matched pixel
inside the ball box counts. Error and MAE are relative to the tape distance.
Figure: lab_test02 at 4.6 s.
