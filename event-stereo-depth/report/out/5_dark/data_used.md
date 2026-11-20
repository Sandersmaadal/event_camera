# Data used: section 5, the dark recording

Recording: `/home/selma/Documents/Project/data_collection/lab/lab_test07` (event cameras .npz, RealSense `_realsense.db3`), 0-13.8 s
(the light comes on at about 14 s). Calibration `/home/selma/Documents/Project/data_collection/sessions/lab_kalibrering/config`, row shift -2.

This recording has no `_info.json`, so the RealSense time comes from the start second in the
`.raw` header (realsense_ball.py; good to about ±0.5 s). The two tracks line up within a frame
on three throws, so the real error is much smaller.

Commands (also in `events/log.txt` and `realsense/log.txt`):
- `depth_events.py lab_test07 --config ... --row-shift -2 --max-disp 200` (noise filter
  5 ms by default)
- `realsense_ball.py lab_test07 --max-depth-m 2`
- ball in the events per 50 ms step from the last 20 ms: tests/compare_ball_tracks.py's
  event_track (8 px cells, at least 30 matched events, about one ball wide)
- pairs: each ok RealSense ball with the nearest event ball within 40 ms

There is no ground truth here: the comparison shows where the two sensors agree, and where
only one of them reports a ball. views.png: 2.5 s, as recorded.
