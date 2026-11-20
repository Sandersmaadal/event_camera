"""Reading the RealSense recordings (<recording>_realsense.db3, a ROS2 bag in sqlite).

    rs = RealSense("lab_test02_realsense.db3")
    rs.depth_times_us          capture time of every depth frame, on the system clock
    rs.depth(i)                depth frame i in metres (0 = no depth)
    rs.color(i)                colour frame i (BGR), at rs.color_times_us[i]
    rs.depth_K                 3 x 3 intrinsics of the depth image

Times are the camera's capture time converted to the host clock by librealsense
("Global Time"), the same clock as the event recordings' system time. Only
numpy, opencv and the standard library are needed: the few message types used
are decoded here directly from their CDR bytes.
"""
import sqlite3
import struct

import cv2
import numpy as np

DEPTH_TOPIC = "/device_0/sensor_0/Depth_0"
COLOR_TOPIC = "/device_0/sensor_1/Color_0"


class _Cdr:
    """Minimal reader for ROS2 CDR (little endian) messages."""

    def __init__(self, data):
        self.b, self.i = data, 4          # skip the 4-byte encapsulation header

    def _align(self, n):
        self.i += (-(self.i - 4)) % n

    def u32(self):
        self._align(4)
        v = struct.unpack_from("<I", self.b, self.i)[0]
        self.i += 4
        return v

    def string(self):
        n = self.u32()
        s = self.b[self.i:self.i + n - 1].decode()
        self.i += n
        return s

    def f64s(self, n):
        self._align(8)
        v = struct.unpack_from(f"<{n}d", self.b, self.i)
        self.i += 8 * n
        return np.array(v)

    def header(self):
        sec, nsec = self.u32(), self.u32()
        return sec + nsec * 1e-9, self.string()


def _metadata(text):
    """'key=value;key=value;' metadata string -> dict."""
    out = {}
    for item in text.split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k] = v
    return out


class RealSense:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.topics = dict(self.db.execute("select name, id from topics"))
        self.depth_rows, self.depth_times_us, self.depth_meta = self._frames(DEPTH_TOPIC, "compressedDepth")
        self.color_rows, self.color_times_us, self.color_meta = self._frames(COLOR_TOPIC, "compressed")
        self.depth_K, self.depth_size = self._intrinsics(DEPTH_TOPIC)
        self.color_K, self.color_size = self._intrinsics(COLOR_TOPIC)
        self.depth_units = float(self.depth_meta[0].get("depth_units", 0.001))
        self.color_R, self.color_t = self._extrinsics(COLOR_TOPIC)

    def _extrinsics(self, sensor):
        """Pose of the stream in the depth frame: p_depth = R @ p_stream + t (metres)."""
        text = _Cdr(self._messages(sensor + "/tf/ref_0")[0][1]).string()
        m = _metadata(text)
        R = np.array([float(v) for v in m["rotation"].split(",")]).reshape(3, 3)
        t = np.array([float(v) for v in m["translation"].split(",")])
        return R, t

    def color_to_depth_px(self, u, v, z):
        """Colour pixel(s) of a point at depth z (metres, colour frame) -> depth image pixel(s)."""
        rays = np.linalg.inv(self.color_K) @ np.vstack([u, v, np.ones_like(u, dtype=float)])
        p = self.color_R @ (rays * z) + self.color_t[:, None]
        q = self.depth_K @ p
        return q[0] / q[2], q[1] / q[2]

    def _messages(self, topic):
        return self.db.execute("select timestamp, data from messages where topic_id = ? order by timestamp",
                               (self.topics[topic],)).fetchall()

    def _frames(self, sensor, kind):
        """Image rows and capture times; image and metadata messages share the bag timestamp."""
        meta = {ts: _metadata(_Cdr(d).string()) for ts, d in self._messages(sensor + "/image/metadata")}
        rows = self.db.execute("select timestamp, id from messages where topic_id = ? order by timestamp",
                               (self.topics[f"{sensor}/image/data/{kind}"],)).fetchall()
        rows = [(ts, rid) for ts, rid in rows if ts in meta]
        metas = [meta[ts] for ts, _ in rows]
        times = np.array([float(m["timestamp"]) * 1e3 for m in metas])     # ms -> us
        return [rid for _, rid in rows], times, metas

    def _intrinsics(self, sensor):
        r = _Cdr(self._messages(sensor + "/image/camera_info")[0][1])
        r.header()
        h, w = r.u32(), r.u32()
        r.string()                       # distortion model
        r.f64s(r.u32())                  # distortion coefficients
        return r.f64s(9).reshape(3, 3), (w, h)

    def _image(self, row_id):
        data = self.db.execute("select data from messages where id = ?", (row_id,)).fetchone()[0]
        r = _Cdr(data)
        r.header()
        r.string()                       # format
        n = r.u32()
        payload = data[r.i:r.i + n]
        start = payload.find(b"\x89PNG")  # compressedDepth has a small config header before the PNG
        return cv2.imdecode(np.frombuffer(payload[max(start, 0):], np.uint8), cv2.IMREAD_UNCHANGED)

    def depth(self, i):
        return self._image(self.depth_rows[i]).astype(np.float32) * self.depth_units

    def color(self, i):
        return self._image(self.color_rows[i])

    def exposure_ms(self, i):
        return float(self.depth_meta[i].get("Actual Exposure", "nan")) / 1e3
