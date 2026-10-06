"""Event containers and file IO.

Recordings are stored as .npz (x, y, p, t, width, height) so that everything
after recording runs without the Metavision SDK. RAW files are read through
metavision_core, which is only needed on the machine that has the cameras.
"""
import os
from dataclasses import dataclass

import numpy as np


@dataclass
class Events:
    x: np.ndarray        # uint16
    y: np.ndarray        # uint16
    on: np.ndarray       # bool, True = ON (brighter) event
    t: np.ndarray        # int64, microseconds, sorted
    width: int
    height: int

    def __len__(self):
        return self.t.size

    def window(self, t0, t1):
        """Indices [i0, i1) of the events with t0 <= t < t1."""
        i0, i1 = np.searchsorted(self.t, [t0, t1])
        return int(i0), int(i1)


def _finish(x, y, p, t, width, height):
    t = np.asarray(t, dtype=np.int64)
    x = np.asarray(x, dtype=np.uint16)
    y = np.asarray(y, dtype=np.uint16)
    on = np.asarray(p) > 0
    if t.size > 1 and np.any(np.diff(t) < 0):
        order = np.argsort(t, kind="stable")
        x, y, on, t = x[order], y[order], on[order], t[order]
    return Events(x, y, on, t, int(width), int(height))


def read_raw(path, chunk_us=100_000):
    """Read a Prophesee RAW (or Metavision HDF5) file. Needs metavision_core.

    Time shifting is turned off so that two hardware-synced recordings keep
    their common time base.
    """
    try:
        from metavision_core.event_io import EventsIterator
    except ImportError as e:
        raise RuntimeError(
            f"Reading {path} needs the Metavision SDK (metavision_core). "
            "Convert it to .npz on the machine that has the SDK: "
            "python convert.py <file.raw>") from e
    if path.endswith(".raw"):
        it = EventsIterator(path, delta_t=chunk_us, do_time_shifting=False)
    else:
        it = EventsIterator(path, delta_t=chunk_us)
    height, width = it.get_size()
    # Keep each field in its smallest type from the start: long recordings
    # hold tens of millions of events and the Pi has limited memory.
    xs, ys, ps, ts = [], [], [], []
    for ev in it:
        if ev.size:
            xs.append(ev["x"].astype(np.uint16))
            ys.append(ev["y"].astype(np.uint16))
            ps.append(ev["p"] > 0)
            ts.append(ev["t"].astype(np.int64))
    if not ts:
        empty = np.zeros(0)
        return _finish(empty, empty, empty, empty, width, height)
    return _finish(np.concatenate(xs), np.concatenate(ys), np.concatenate(ps), np.concatenate(ts),
                   width, height)


def save_npz(path, ev):
    np.savez_compressed(path, x=ev.x, y=ev.y, p=ev.on.astype(np.uint8), t=ev.t,
                        width=ev.width, height=ev.height)


def load_events(path):
    """Load events from .npz, or from .raw / .hdf5 when the SDK is installed."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    if path.endswith(".npz"):
        d = np.load(path)
        return _finish(d["x"], d["y"], d["p"], d["t"], d["width"], d["height"])
    return read_raw(path)
