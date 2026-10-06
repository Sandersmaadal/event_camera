"""Reading a session's views and review decisions."""
import json
import os

import numpy as np

SIDES = ("left", "right")


def load_views(session):
    path = os.path.join(session, "views.json")
    if not os.path.exists(path):
        raise SystemExit(f"{path} not found. Run: python detect.py {session}")
    with open(path) as f:
        return json.load(f)


def load_review(session):
    """{view id (str): {"left": bool, "right": bool}}; missing = not reviewed."""
    path = os.path.join(session, "review.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_review(session, review):
    with open(os.path.join(session, "review.json"), "w") as f:
        json.dump(review, f, indent=1)


def usable(view, side, review):
    """True when this view has corners for this camera and was not rejected."""
    if side not in view:
        return False
    return review.get(str(view["id"]), {}).get(side, True)


def corners(view, side):
    return np.asarray(view[side]["corners"], dtype=np.float64)
