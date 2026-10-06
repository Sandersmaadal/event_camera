#!/usr/bin/env python3
"""Step 1: record the flickering checkerboard with both cameras (run on the Pi).

    python record.py sessions/tv01
    python record.py sessions/tv01 --side left      # one camera only

Records the native RAW stream of each camera, with the same hardware-sync
setup as yug3nn's record_stereo.py (left = slave, right = master), and then
converts the recordings to left.npz / right.npz so that the rest of the
pipeline runs without the Metavision SDK, on the Pi or on another machine.

How to move the rig while recording:
  - Put the rig down, or brace it against something, and keep it STILL for
    2 to 3 seconds. Then move to the next pose. Repeat 40 to 60 times.
  - Only the still periods are used. Flips that happen while you move are
    ignored later, so you do not have to hurry or time anything.
  - Vary the pose: board in every part of the image including the edges and
    corners, tilted up to ~30 degrees left/right/up/down, near and far.
  - The whole board must be visible in BOTH cameras for the pose to count
    for the stereo calibration.

Stop with q in the preview window, or Enter in the terminal.
"""
import argparse
import os
import select
import sys
import threading
import time

import numpy as np

from evcalib import settings as S
from evcalib.events import read_raw, save_npz


class Recorder(threading.Thread):
    """Opens one camera, sets its sync role and bias, and logs RAW until stopped."""

    def __init__(self, serial, role, raw_path, bias_increment):
        super().__init__(daemon=True)
        self.serial, self.role, self.raw_path = serial, role.lower(), raw_path
        self.bias_increment = bias_increment
        self.running = True
        self.ready = threading.Event()
        self.error = None
        self.latest = None
        self.size = (320, 320)
        self.n_events = 0

    def run(self):
        try:
            from metavision_core.event_io import EventsIterator
            it = EventsIterator(input_path=self.serial, delta_t=20000)
            device = it.reader.device
            self.size = it.get_size()                      # (height, width)
            sync = device.get_i_camera_synchronization()
            if sync and self.role == "master":
                sync.set_mode_master()
            elif sync and self.role == "slave":
                sync.set_mode_slave()
            if self.bias_increment:
                biases = device.get_i_ll_biases()
                if biases:
                    biases.set("bias_diff_on", biases.get("bias_diff_on") + self.bias_increment)
                    biases.set("bias_diff_off", biases.get("bias_diff_off") + self.bias_increment)
            stream = device.get_i_events_stream()
            stream.log_raw_data(self.raw_path)
            self.ready.set()
            for evs in it:
                if not self.running:
                    break
                self.n_events += evs.size
                self.latest = evs.copy()
            stream.stop_log_raw_data()
        except Exception as e:                              # report in the main thread
            self.error = e
            self.ready.set()


def preview_image(evs, size):
    h, w = size
    img = np.zeros((h, w), np.uint8)
    if evs is not None and evs.size:
        img[evs["y"], evs["x"]] = np.where(evs["p"] > 0, 255, 110).astype(np.uint8)
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", help="output folder, e.g. sessions/tv01")
    ap.add_argument("--side", choices=["both", "left", "right"], default="both")
    ap.add_argument("--duration", type=float, help="stop automatically after this many seconds")
    ap.add_argument("--headless", action="store_true", help="no preview window")
    ap.add_argument("--keep-raw-only", action="store_true", help="do not convert to .npz afterwards")
    args = ap.parse_args()
    os.makedirs(args.session, exist_ok=True)

    cams = []
    if args.side in ("both", "left"):
        role = S.LEFT_ROLE if args.side == "both" else "standalone"
        cams.append(("left", Recorder(S.SERIAL_LEFT, role, os.path.join(args.session, "left.raw"), S.BIAS_INCREMENT)))
    if args.side in ("both", "right"):
        role = S.RIGHT_ROLE if args.side == "both" else "standalone"
        cams.append(("right", Recorder(S.SERIAL_RIGHT, role, os.path.join(args.session, "right.raw"), S.BIAS_INCREMENT)))
    # The slave must be waiting before the master starts its clock.
    cams.sort(key=lambda c: c[1].role != "slave")
    for name, cam in cams:
        cam.start()
        if not cam.ready.wait(15) or cam.error:
            sys.exit(f"Could not start the {name} camera ({cam.serial}): {cam.error or 'timeout'}")
        print(f"{name}: recording as {cam.role} -> {cam.raw_path}")
        time.sleep(0.5)

    show = not args.headless
    if show:
        import cv2
    print("\nRecording. Hold each pose still for 2-3 s. Press q in the window or Enter here to stop.\n")
    t_begin = time.time()
    try:
        while True:
            elapsed = time.time() - t_begin
            if args.duration and elapsed > args.duration:
                break
            if any(c.error for _, c in cams):
                break
            if show:
                view = np.hstack([preview_image(c.latest, c.size) for _, c in sorted(cams)])
                cv2.putText(view, f"{elapsed:5.1f} s", (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1)
                cv2.imshow("recording (q to stop)", view)
                if cv2.waitKey(20) & 0xFF == ord("q"):
                    break
            else:
                time.sleep(0.05)
            if sys.stdin.isatty() and sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                break
    except KeyboardInterrupt:
        pass
    # Stop the slave first: it needs the master's clock to finish cleanly.
    for name, cam in sorted(cams, key=lambda c: c[1].role != "slave"):
        cam.running = False
        cam.join(timeout=10)
        if cam.is_alive():
            print(f"WARNING: the {name} camera did not stop cleanly; its RAW file may be incomplete.")
    if show:
        cv2.destroyAllWindows()
    for name, cam in cams:
        if cam.error:
            print(f"ERROR in the {name} camera: {cam.error}")
        print(f"{name}: {cam.n_events:,} events in {time.time() - t_begin:.0f} s")

    if not args.keep_raw_only:
        for name, cam in cams:
            print(f"converting {cam.raw_path} ...")
            save_npz(os.path.join(args.session, f"{name}.npz"), read_raw(cam.raw_path))
    print(f"\nNext: python detect.py {args.session}")


if __name__ == "__main__":
    main()
