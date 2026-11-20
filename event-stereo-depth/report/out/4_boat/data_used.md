# Data used: section 4, the boat (experiment 2)

Recording: `/home/selma/Documents/Project/data_collection/recordings/datacololection_test02` (event cameras and RealSense), 9.5-31.5 s, while Buster is
in view. Cameras standing still on land.

GNSS: `/home/selma/Documents/Project/data_collection/gnss/exp2/relative.csv` (gnss/extract_gnss.py): Buster's standalone 1 Hz fixes relative to the median
position of the same receiver standing 0.45 m behind the cameras (pretest-capture and
test0, 1447 fixes, spread 0.25 m). Standalone fixes can be off by 1-2 m; much of that is shared
by both positions, because they come from the same receiver about 30 minutes apart.

Time: clock offset 70843.0 s (real UTC = camera system time + offset), fitted from
Buster's direction (image column against GNSS bearing, rms 1.5 deg); offsets 1 s
either side fit almost as well, so about ±1 s, which is ±0.4 m of Buster's distance. Camera viewing
direction from the same fit: 49.6 deg from north.

Calibration: `/home/selma/Documents/Project/data_collection/sessions/lab_kalibrering/config`, row shift -6 (check_rectification.py on 10-31 s gives a median of
-5.9 rows with the lab calibration).

**The lab calibration does not fit this recording.** The rows are off by about 6 (a camera
turned about 1 deg after this recording or before the lab calibration). A sideways turn of
the same size would bias the depth, and this check cannot see it. With the lab calibration
the event cameras put Buster at 8-10 m, the RealSense at 12-14 m and GNSS at 16-19 m
(10-20 s). Use the harbour calibration (recordings/calibration, 2026-10-19) for the event
depth. The GNSS distance is also in doubt: the RealSense sees Buster pass in front of the
mooring pole (about 16 m away by the RealSense), while the GNSS distance puts it behind, and
Buster's size in the colour image (31 deg at 18 s, almost broadside) fits a 5-6 m boat at about
10-12 m, not at 17 m. The receiver stood 45 cm behind the cameras as assumed, so the likely
cause is the standalone fixes themselves (the camera spot is next to a large building, which
can bias a standalone fix by metres); post-processing the raw .ubx logs would show it.

RealSense: per second, the median depth of the biggest blob closer than the background (the median
of the first 8 s, before Buster is in view) by at least 1.5 m; that blob is Buster.

Depth: `depth_events.py` with the defaults (noise filter 5 ms), --max-disp 64. Per second,
the median depth of the matched events in rows 90-230 within 60 px of Buster's centre
column. GNSS depth: Buster's antenna along the viewing direction, minus 0.45 m.

The antenna is inside the boat, but the event cameras see mostly the outside of the hull (its
edges, on the side facing the cameras). So the event depth should be shorter than the GNSS
depth: by about half the beam (about 1 m) when Buster is broadside, and up to about half its
length when it is turned towards the cameras (here 120-140 deg between its heading and the
line of sight, so up to about 2 m).
