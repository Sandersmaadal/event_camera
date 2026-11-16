Row shift -2 (unless the method sets its own), step 50 ms.

## lab_test01: ball at 1 m

| Method | Points | Steps | Median | Error | MAE | Within ±5 % | Within ±10 % | Compute per s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| count_zncc | 3393 | 40/42 | 1.011 m | +1.1 % | 73.1 % | 72 % | 91 % | 15.25 s |
| count_census | 5011 | 39/42 | 1.012 m | +1.2 % | 11.1 % | 79 % | 97 % | 12.67 s |
| voxel_zncc | 5271 | 34/42 | 1.012 m | +1.2 % | 10.5 % | 77 % | 98 % | 19.98 s |
| voxel_census | 5971 | 33/42 | 1.011 m | +1.1 % | 3.3 % | 82 % | 100 % | 14.13 s |
| voxel_census_no_row_shift | 4398 | 31/42 | 1.017 m | +1.7 % | 7.9 % | 82 % | 98 % | 14.39 s |
| events | 4745 | 26/42 | 1.015 m | +1.5 % | 2.8 % | 82 % | 100 % | 0.53 s |

## lab_test02: ball at 2 m

| Method | Points | Steps | Median | Error | MAE | Within ±5 % | Within ±10 % | Compute per s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| count_zncc | 1148 | 16/16 | 1.999 m | -0.0 % | 9.3 % | 95 % | 95 % | 13.58 s |
| count_census | 1418 | 16/16 | 2.000 m | +0.0 % | 4.7 % | 99 % | 99 % | 11.00 s |
| voxel_zncc | 1544 | 16/16 | 1.997 m | -0.2 % | 0.7 % | 100 % | 100 % | 17.94 s |
| voxel_census | 1534 | 16/16 | 1.999 m | -0.0 % | 2.3 % | 99 % | 99 % | 12.80 s |
| voxel_census_no_row_shift | 876 | 16/16 | 1.990 m | -0.5 % | 1.8 % | 99 % | 99 % | 12.56 s |
| events | 1402 | 16/16 | 1.980 m | -1.0 % | 1.0 % | 100 % | 100 % | 0.67 s |

## lab_test03: ball at 3 m

| Method | Points | Steps | Median | Error | MAE | Within ±5 % | Within ±10 % | Compute per s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| count_zncc | 551 | 18/18 | 2.905 m | -3.2 % | 15.5 % | 87 % | 93 % | 15.12 s |
| count_census | 596 | 18/18 | 2.896 m | -3.5 % | 4.7 % | 91 % | 98 % | 12.32 s |
| voxel_zncc | 779 | 18/18 | 2.896 m | -3.5 % | 3.9 % | 94 % | 100 % | 19.16 s |
| voxel_census | 731 | 18/18 | 2.893 m | -3.6 % | 3.9 % | 94 % | 99 % | 13.78 s |
| voxel_census_no_row_shift | 102 | 14/18 | 2.957 m | -1.4 % | 19.2 % | 74 % | 91 % | 13.82 s |
| events | 395 | 18/18 | 2.898 m | -3.4 % | 3.5 % | 95 % | 100 % | 0.24 s |
