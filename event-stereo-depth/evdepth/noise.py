"""Noise filtering of one camera's events, before rectification.

    ev = background_activity(ev, dt_us=2000)

Background activity filter: an event is kept when one of its 8 neighbouring
pixels had an event at most dt_us before it. Edges of moving objects make
neighbouring pixels fire close together in time; noise events (the "background
activity" that dominates in the dark) and hot pixels fire alone. The loop runs in
C++ (cpp/noise_filter.cpp), because it has to go through the events one by one.
"""
from dataclasses import replace

try:
    from evdepth import _evmatch
except ImportError:          # not built: see cpp/build.sh
    _evmatch = None


def background_activity(ev, dt_us):
    """The events of `ev` (an evcalib Events) that have a neighbour at most dt_us before them."""
    if _evmatch is None:
        raise SystemExit("The noise filter needs the C++ module. Run cpp/build.sh.")
    keep = _evmatch.background_activity_filter(ev.x, ev.y, ev.t, ev.width, ev.height, int(dt_us))
    return replace(ev, x=ev.x[keep], y=ev.y[keep], on=ev.on[keep], t=ev.t[keep])
