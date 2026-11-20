# Report figures and tables

One script per section. Each writes to `out/<section>/`: figures (`.png` and `.pdf`),
`table.md` / `table.csv`, and `data_used.md` with the recordings, time windows and settings
behind the numbers. Runs are stored in the same folder and reused; delete a folder to
compute it again.

```bash
python report/s1_representations.py     # about 6 min
python report/s2_matching.py            # about 3 min
python report/s3_realsense.py           # after s2 (uses its event runs)
python report/s4_boat.py                # [--config <harbour calibration> --row-shift <rows>]
python report/s5_dark.py
```

Shared settings (`common.py`): lab calibration `sessions/lab_kalibrering`, row shift -2,
noise filter 5 ms, a 20 ms window every 50 ms, disparities 0-127.

`views.png` (sections 3, 4, 5) is one moment exactly as recorded: the raw events of both
event cameras (not rectified, no noise filter), the RealSense colour frame and its raw depth
in metres (0 = no depth). The raw events in section 1 are the same. The representations,
matching and depth use the noise-filtered, rectified events.

| Section | Data | Figures | Result |
| --- | --- | --- | --- |
| 1. Representations | lab_test01-03 (ball at 1, 2, 3 m), census matching | `representations` | `voxel` is best: the most points with the lowest error (MAE 2.4 / 0.5 / 3.3 %). The time surfaces find 4-25x fewer points |
| 2. Matching methods | lab_test01-03 | `depth_over_time`, `example` | Both are equally accurate (MAE 0.5-3.5 %); event by event is 30-70x faster (0.2-0.4 s per second of recording) |
| 3. Event cameras vs RealSense | lab_test01-03 | `views`, `depth_over_time` | The RealSense agrees with the tape to 2-6 cm; the event depth is short by 1.4 / 3.8 / 5.0 % against it |
| 4. Boat vs GNSS | experiment 2 (cameras on land) | `views`, `sync`, `depth_over_time` | **Not final**: the lab calibration does not fit the harbour rig, and GNSS and RealSense disagree (see below) |
| 5. Dark | lab_test07 | `views`, `tracks` | The event cameras keep the ball as a sharp blob; the RealSense smears it. Where both find it, 90 % agree within ±10 % |

## Section 4: what is missing

- **Calibration.** With the lab calibration the rows are off by about 6 on the harbour
  recording, so a camera turned by about 1° between 19 Oct and the lab calibration. The
  event depth needs the harbour day's own calibration: `recordings/calibration` (19 Oct),
  through `event-stereo-calib` (detect.py, review.py, calibrate.py). Then run
  `check_rectification.py` on `datacololection_test02` again and pass `--config` and
  `--row-shift` to `s4_boat.py` (delete `out/4_boat/events/` first).
- **GNSS reference.** The clock sync works: Buster's direction from GNSS and from the event
  image agree to 1.5° rms, and the clock is found to about ±1 s. But the distance does
  not: GNSS puts Buster at 16-19 m (10-20 s), the RealSense at 12-14 m. Two checks point to
  the GNSS distance being too long: in the RealSense image Buster passes in front of the
  mooring pole, which the RealSense measures at about 16 m; and Buster's size in the colour
  image (31° at 18 s, almost broadside) fits a 5-6 m boat at about 10-12 m. The receiver stood
  45 cm behind the cameras, as the script assumes, so the likely cause is the standalone fixes
  themselves (a building next to the camera spot can bias them by metres). Post-processing the
  raw `.ubx` logs (PPK) would show it; Buster's exact length would make the size check firm.
- **Hull against antenna.** The GNSS antenna is inside the boat; the event cameras see the
  outside of the hull. Expect the event depth to be about 1 m (broadside) to 2 m (turned
  towards the cameras) shorter than the GNSS depth.
