"""Global settings. Edit these to match your rig and your screen."""

# --- Cameras (Prophesee GenX320) -------------------------------------------
SERIAL_LEFT = "genx320 11-003c"   # run `metavision_platform_info` to get yours
SERIAL_RIGHT = "genx320 10-003c"
LEFT_ROLE = "slave"               # hardware sync role, as in yug3nn's setup
RIGHT_ROLE = "master"
BIAS_INCREMENT = 5                # added to bias_diff_on / bias_diff_off while recording

# --- Board shown on the screen ----------------------------------------------
# The HTML page shows 10 x 7 squares, which gives 9 x 6 inner corners.
BOARD_COLS = 9                    # inner corners along the screen's horizontal axis
BOARD_ROWS = 6                    # inner corners along the screen's vertical axis
# Measure these ON THE TV with a ruler: total board width / 10 and total
# board height / 7. They must be re-measured for every screen you use.
# None = calibrate.py refuses to run until you set them (or pass --square-mm).
SQUARE_W_MM = 85
SQUARE_H_MM = 85               # None = same as SQUARE_W_MM
FLIP_PERIOD_MS = 400              # FREQ_MS in the HTML page

# --- Flip detection ----------------------------------------------------------
RATE_BIN_US = 1000                # event-rate histogram bin
RATE_SMOOTH_MS = 8                # box smoothing of the event rate
MIN_FLIP_CONTRAST = 2.0           # burst rate / rate just before and after it
MIN_WINDOW_BEFORE_MS = 8          # a flip window always covers at least this much before
MIN_WINDOW_AFTER_MS = 14          # ... and after the burst peak (screen refresh + pixel response)
MAX_HALF_WINDOW_MS = 60           # and never extends further than this
SYNC_TOL_MS = 30                  # left and right flips closer than this are the same flip

# --- Board detection ---------------------------------------------------------
MIN_CORNER_SPACING_PX = 3.0       # reject boards smaller than this (corner to corner)

# --- Grouping flips into static poses ---------------------------------------
POSE_TOL_PX = 0.2                 # the board may not shift more than this between flips of a pose
MAX_CORNER_NOISE_PX = 1.0         # mean corner difference above this is not the same detection
MIN_FLIPS_PER_POSE = 1            # a pose seen in fewer flips is treated as "moving" (1 = keep every detection)
MAX_FLIPS_GAP = 2.5               # a pose ends after this many flip periods without a flip
MAX_POSE_SCATTER_PX = 0.35        # poses with more corner scatter are flagged in review

# --- Calibration -------------------------------------------------------------
FIX_K3 = True                     # 4-parameter distortion (k1, k2, p1, p2)
MAX_VIEW_RMS_PX = 1.0             # hard limit on a single view's reprojection RMS
OUTLIER_MADS = 3.5                # robust outlier limit: median + this * MAD
MIN_VIEWS = 15                    # fewer views than this is reported as a warning
