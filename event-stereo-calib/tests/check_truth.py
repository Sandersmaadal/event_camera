"""Compare the calibration of a simulated session with its ground truth.

    python tests/check_truth.py sessions/sim

Exits with an error if the result is further from the truth than a 320x320
sensor should give.
"""
import json
import os
import sys

import cv2
import numpy as np


def main():
    session = sys.argv[1]
    with open(os.path.join(session, "ground_truth.json")) as f:
        gt = json.load(f)
    worst = []
    for side in ("left", "right"):
        with open(os.path.join(session, "config", f"camera_{side}.json")) as f:
            cam = json.load(f)
        dk = np.array(cam["K"]) - np.array(gt[f"K_{side}"])
        err = np.abs([dk[0, 0], dk[1, 1], dk[0, 2], dk[1, 2]])
        print(f"{side:5s}: fx, fy, cx, cy off by {np.round(err, 2)} px, RMS {cam['RMS']:.3f} px, "
              f"{cam['n_images_used']} views")
        worst.append(err.max() < 1.0)
    with open(os.path.join(session, "config", "stereo_params.json")) as f:
        st = json.load(f)
    T, T_gt = np.array(st["T"]).ravel(), np.array(gt["T"])
    dR = np.array(st["R"]) @ cv2.Rodrigues(np.array(gt["rvec"]))[0].T
    rot_err = np.degrees(np.linalg.norm(cv2.Rodrigues(dR)[0]))
    base_err = abs(np.linalg.norm(T) - np.linalg.norm(T_gt))
    print(f"stereo: baseline {np.linalg.norm(T):.2f} mm (truth {np.linalg.norm(T_gt):.2f}), "
          f"T off by {np.round(T - T_gt, 2)} mm, rotation off by {rot_err:.3f} deg, "
          f"epipolar {st['epipolar_mean_px']:.3f} px")
    worst += [base_err < 1.0, rot_err < 0.3]
    if not all(worst):
        sys.exit("FAILED: the calibration is too far from the ground truth")
    print("OK")


if __name__ == "__main__":
    main()
