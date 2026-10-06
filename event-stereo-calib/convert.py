#!/usr/bin/env python3
"""Convert Prophesee RAW recordings to .npz (needs the Metavision SDK).

    python convert.py sessions/tv01                 # left.raw and right.raw in a session
    python convert.py some/left.raw some/right.raw  # any RAW files, written next to them

record.py already does this at the end of a recording. Use this script for
recordings made with other tools, for example yug3nn's record_stereo.py:
copy or rename the two files to <session>/left.raw and <session>/right.raw.
"""
import argparse
import os

from evcalib.events import read_raw, save_npz


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="a session folder, or RAW files")
    args = ap.parse_args()
    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in ("left.raw", "right.raw") if os.path.exists(os.path.join(p, f))]
        else:
            files.append(p)
    if not files:
        raise SystemExit("No RAW files found.")
    for raw in files:
        ev = read_raw(raw)
        out = os.path.splitext(raw)[0] + ".npz"
        save_npz(out, ev)
        dur = (ev.t[-1] - ev.t[0]) / 1e6 if len(ev) else 0
        print(f"{raw} -> {out}: {len(ev):,} events, {dur:.1f} s, {ev.width}x{ev.height}")


if __name__ == "__main__":
    main()
