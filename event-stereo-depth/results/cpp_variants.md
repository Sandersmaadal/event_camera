# C++ event matcher variants (2026-11-16)

`depth_events.py` on the three lab tests (`--row-shift -2 --max-disp 128`,
ball boxes as in `DECISIONS.md`). "Near whole px" is the share of sub-pixel
disparities within 0.1 px of a whole number (20 % if spread evenly; more
means the disparities bunch at whole pixels). Compute is seconds of
computing per second of recording, 16 threads. Percentages rounded to whole
numbers (the exact values of the kept variant are in
`lab_after_cleanup/results.csv`: 99.9 %, 100 % and 99.7 % within ±10 %).

| Variant | Test | Points | Median | Error | MAE | ±5 % | ±10 % | Compute | Near whole px |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| no left-right check, parabola | 1 m | 5628 | 1.017 m | +1.7 % | 3.0 % | 81 % | 99 % | 0.40 s | 31 % |
| no left-right check, parabola | 2 m | 1439 | 1.980 m | -1.0 % | 1.3 % | 100 % | 100 % | 0.47 s | 22 % |
| no left-right check, parabola | 3 m | 408 | 2.898 m | -3.4 % | 4.9 % | 92 % | 98 % | 0.20 s | 55 % |
| no left-right check, from events | 1 m | 5628 | 1.015 m | +1.5 % | 3.0 % | 81 % | 99 % | 0.41 s | 36 % |
| no left-right check, from events | 2 m | 1439 | 1.982 m | -0.9 % | 1.3 % | 100 % | 100 % | 0.50 s | 30 % |
| no left-right check, from events | 3 m | 408 | 2.895 m | -3.5 % | 5.0 % | 92 % | 98 % | 0.22 s | 37 % |
| left-right check, parabola (kept) | 1 m | 4745 | 1.015 m | +1.5 % | 2.8 % | 82 % | 100 % | 0.62 s | 31 % |
| left-right check, parabola (kept) | 2 m | 1402 | 1.980 m | -1.0 % | 1.0 % | 100 % | 100 % | 0.70 s | 22 % |
| left-right check, parabola (kept) | 3 m | 395 | 2.898 m | -3.4 % | 3.5 % | 95 % | 100 % | 0.28 s | 55 % |
| left-right check, from events | 1 m | 4745 | 1.014 m | +1.4 % | 2.8 % | 82 % | 100 % | 0.62 s | 35 % |
| left-right check, from events | 2 m | 1402 | 1.982 m | -0.9 % | 1.0 % | 100 % | 100 % | 0.65 s | 30 % |
| left-right check, from events | 3 m | 395 | 2.895 m | -3.5 % | 3.6 % | 95 % | 100 % | 0.30 s | 37 % |
| left-right check, from events, fast settings | 1 m | 4204 | 1.018 m | +1.8 % | 10.1 % | 79 % | 99 % | 0.22 s | 28 % |
| left-right check, from events, fast settings | 2 m | 1230 | 1.986 m | -0.7 % | 2.3 % | 99 % | 99 % | 0.30 s | 25 % |
| left-right check, from events, fast settings | 3 m | 485 | 2.893 m | -3.6 % | 6.9 % | 82 % | 96 % | 0.11 s | 24 % |

Speed on the 2 m ball (190 000 left events in 0.8 s), no left-right check:
1 thread 13.2 us per event (3.1 s per second of recording), 16 threads
1.9 us per event (0.46 s), identical results. The multi-threaded version with
the left-right check off and the parabola gives exactly the same disparities
as the first single-threaded version.

"From events": each recent left event is paired with the right event closest
in time at the best disparity ±1, and the disparity is the weighted mean of
their sub-pixel x differences. That variant was removed from the code (it
was not better, see DECISIONS.md, decision 6).
