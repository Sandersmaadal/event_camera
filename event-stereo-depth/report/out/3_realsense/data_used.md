# Data used: section 3, event cameras against the RealSense

Recordings: `/home/selma/Documents/Project/data_collection/lab/lab_test01`, `lab_test02`, `lab_test03`: the event cameras (left/right .npz)
and the RealSense (`*_realsense.db3`: depth 1280 x 720 and colour 640 x 480 at 15 fps), on the
same clock through the clock anchor in `*_info.json`.

Event cameras: the event-by-event runs of section 2 (`../2_matching/runs/*_events/`), median
depth of the points in the ball box per step. Ball boxes and time ranges as in section 2.

RealSense: `realsense_ball.py` (default settings), output in `realsense/<test>/ball.csv` (with a
crop of every frame there if run with `--sheet`). Ok frames inside the time ranges only.

Pairing: each event step (middle of its 20 ms window) with the nearest RealSense frame
within 70 ms. views.png: lab_test02 at 4.6 s, as recorded.
