#!/usr/bin/env python3
"""Collect the usable GNSS data from the harbour tests (2026-10-19), one folder per experiment.

    python gnss/extract_gnss.py --data ~/Documents/Project/data_collection \\
        --out ~/Documents/Project/data_collection/gnss

Reads
- buster/*.ubx                 the target boat's u-blox receiver (1 Hz, standalone, raw
                               measurements logged so it can be post-processed later)
- milliampere/stereo_*/*.mcap  the observer boat's ROS2 bags (RTK GNSS, heading, IMU);
                               needs `pip install mcap mcap-ros2-support`
- recordings/*_info.json       camera recording start/stop (on the camera laptop's clock)

Writes to --out
- camera_position/             the receiver standing at the cameras (pretest-capture and
                               test0): position.json with the mean position of experiments 0-3
- expN/                        per experiment:
    buster.csv                 t_utc_s, lat_deg, lon_deg, height_m, h_acc_m, v_north_mps, v_east_mps
    buster.ubx                 copy of the raw log, for post-processing (PPK)
    milliampere_fix.csv        t_utc_s, lat_deg, lon_deg, height_m, status (2 = RTK), std_h_m
    milliampere_heading.csv    t_utc_s, heading_deg (compass, of the dual-antenna baseline)
    milliampere_imu.csv        t_utc_s, gyro x/y/z (rad/s), acc x/y/z (m/s2), orientation quaternion
    relative.csv               buster seen from the observer antenna, at the buster's 1 Hz times:
                               east_m, north_m, range_m, bearing_deg, rel_bearing_deg (from heading)
    info.json                  which files belong together, time windows and the coarse clock offset
- overview.png                 range to buster over time per experiment

All times are UTC seconds (Unix). The camera laptop's clock was about 19 h 41 min behind;
real time = camera system time + clock_offset_s. The offset in info.json only comes from
start times that were set by hand, so it is good to about +-30 s; the exact offset has to be
found from the data (for example buster's bearing against its column in the event image).
Distances are antenna to antenna: not yet corrected for where the cameras sit on milliAmpere
(1-2 m from its antenna, at the edge of the boat) or for buster's hull around its antenna.
"""
import argparse
import calendar
import csv
import glob
import json
import os
import shutil
import struct

import numpy as np

# Which files belong to each experiment. camera: recordings/<name>_info.json; buster: part of
# the .ubx file name (its end, before .ubx); bag: milliampere/<bag>/. observer: "camera_position" (cameras on land)
# or "milliampere" (cameras on the boat).
EXPERIMENTS = {
    "exp1": dict(camera="datacololection_test01", buster="_test1", bag=None, observer="camera_position",
                 note="Cameras still. GNSS moved to buster, buster drives forward."),
    "exp2": dict(camera="datacololection_test02", buster="_test2", bag=None, observer="camera_position",
                 note="Cameras still. Buster drives back."),
    "exp4": dict(camera="datacololection_test04", buster="_test04", bag="stereo_exp4", observer="milliampere",
                 note="On milliAmpere standing still. Buster moves towards us."),
    "exp4b": dict(camera="datacololection_test04b", buster="_test04b", bag="stereo_exp4b", observer="milliampere",
                  note="On milliAmpere standing still. Buster moves past us."),
    "exp6": dict(camera="datacololection_test06", buster="_test5", bag="stereo_exp6", observer="milliampere",
                 note="Both move, diagonal crossing. Many waves. (Buster's log is called test5.)"),
    "exp7": dict(camera="datacololection_test07", buster="_test7", bag="stereo_exp7", observer="milliampere",
                 note="Buster starts in front of us and moves away. We stand still."),
}
# Receiver standing at the cameras for experiments 0-3 ("45 cm bak er GPS": 45 cm behind them).
CAMERA_POSITION_LOGS = ["_pretest-capture", "-test0"]


# ---------------------------------------------------------------------------- reading

def read_ubx_pvt(path):
    """NAV-PVT messages of a u-blox log -> array of rows (see buster.csv)."""
    data, rows, i = open(path, "rb").read(), [], 0
    while (i := data.find(b"\xb5\x62", i)) >= 0 and i + 8 <= len(data):
        cls, mid, n = data[i + 2], data[i + 3], struct.unpack_from("<H", data, i + 4)[0]
        if i + 8 + n > len(data):
            break
        if (cls, mid) == (0x01, 0x07) and n == 92:
            p = data[i + 6:i + 6 + n]
            year, month, day, hour, minute, sec = struct.unpack_from("<HBBBBB", p, 4)
            nano = struct.unpack_from("<i", p, 16)[0]
            lon, lat, height, _, h_acc, _ = struct.unpack_from("<iiiiII", p, 24)
            v_north, v_east = struct.unpack_from("<ii", p, 48)
            t = calendar.timegm((year, month, day, hour, minute, sec)) + nano * 1e-9
            rows.append((t, lat * 1e-7, lon * 1e-7, height / 1e3, h_acc / 1e3, v_north / 1e3, v_east / 1e3))
        i += 8 + n
    return np.array(rows)


def read_bag(path):
    """RTK fix, heading and IMU from a milliAmpere bag. Fix times are the receiver's own
    measurement time (/time_reference); heading uses the header stamp minus the same latency."""
    from mcap.reader import make_reader
    from mcap_ros2.decoder import DecoderFactory

    stamp = lambda h: h.stamp.sec + h.stamp.nanosec * 1e-9
    fix, heading, imu, time_ref = [], [], [], {}
    topics = ["/vectorVS330/fix", "/vectorVS330/heading", "/xsens/imu", "/time_reference"]
    with open(path, "rb") as f:
        reader = make_reader(f, decoder_factories=[DecoderFactory()])
        for _, channel, _, m in reader.iter_decoded_messages(topics=topics):
            if channel.topic == "/vectorVS330/fix":
                fix.append((stamp(m.header), m.latitude, m.longitude, m.altitude, m.status.status,
                            np.sqrt(m.position_covariance[0])))
            elif channel.topic == "/vectorVS330/heading":
                q = m.quaternion
                heading.append((stamp(m.header), np.degrees(2 * np.arctan2(q.z, q.w)) % 360))
            elif channel.topic == "/xsens/imu":
                g, a, q = m.angular_velocity, m.linear_acceleration, m.orientation
                imu.append((stamp(m.header), g.x, g.y, g.z, a.x, a.y, a.z, q.x, q.y, q.z, q.w))
            else:
                time_ref[stamp(m.header)] = m.time_ref.sec + m.time_ref.nanosec * 1e-9
    fix, heading, imu = np.array(fix), np.array(heading), np.array(imu)
    lag = np.median([s - time_ref[s] for s in fix[:, 0] if s in time_ref])
    fix[:, 0] = [time_ref.get(s, s - lag) for s in fix[:, 0]]
    heading[:, 0] -= lag
    return fix, heading, imu, lag


# ---------------------------------------------------------------------------- geometry

def east_north(lat, lon, lat0, lon0):
    """Metres east and north of (lat0, lon0) on the WGS84 ellipsoid (fine over a few km)."""
    a, e2 = 6378137.0, 6.69437999014e-3
    s = np.sin(np.radians(lat0)) ** 2
    n_radius = a / np.sqrt(1 - e2 * s)
    m_radius = a * (1 - e2) / (1 - e2 * s) ** 1.5
    return (np.radians(lon - lon0) * n_radius * np.cos(np.radians(lat0)),
            np.radians(lat - lat0) * m_radius)


def interp_angle(t, t_src, deg):
    return np.degrees(np.interp(t, t_src, np.unwrap(np.radians(deg)))) % 360


def relative(buster, observer_fix=None, heading=None, fixed=None):
    """Buster relative to the observer antenna, at the buster's times inside the observer's span."""
    t = buster[:, 0]
    if fixed is not None:
        lat0, lon0 = fixed
        obs_e = obs_n = np.zeros_like(t)
    else:
        lat0, lon0 = observer_fix[0, 1], observer_fix[0, 2]
        keep = (t >= observer_fix[0, 0]) & (t <= observer_fix[-1, 0])
        buster, t = buster[keep], t[keep]
        oe, on = east_north(observer_fix[:, 1], observer_fix[:, 2], lat0, lon0)
        obs_e, obs_n = np.interp(t, observer_fix[:, 0], oe), np.interp(t, observer_fix[:, 0], on)
    be, bn = east_north(buster[:, 1], buster[:, 2], lat0, lon0)
    east, north = be - obs_e, bn - obs_n
    bearing = np.degrees(np.arctan2(east, north)) % 360
    rel = (bearing - interp_angle(t, heading[:, 0], heading[:, 1]) + 180) % 360 - 180 if heading is not None \
        else np.full_like(t, np.nan)
    return np.column_stack([t, east, north, np.hypot(east, north), bearing, rel])


# ---------------------------------------------------------------------------- writing

def write_csv(path, header, rows, fmt):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([fm % v for fm, v in zip(fmt, r)])


def write_buster(path, rows):
    write_csv(path, ["t_utc_s", "lat_deg", "lon_deg", "height_m", "h_acc_m", "v_north_mps", "v_east_mps"],
              rows, ["%.3f", "%.9f", "%.9f", "%.3f", "%.3f", "%.3f", "%.3f"])


def find_ubx(data, part):
    hits = [p for p in glob.glob(os.path.join(data, "buster", "*.ubx")) if os.path.basename(p)[:-4].endswith(part)]
    assert len(hits) == 1, (part, hits)
    return hits[0]


def camera_position(args):
    """Mean position of the receiver standing at the cameras (experiments 0-3)."""
    out = os.path.join(args.out, "camera_position")
    os.makedirs(out, exist_ok=True)
    logs = {}
    for part in CAMERA_POSITION_LOGS:
        path = find_ubx(args.data, part)
        shutil.copy(path, out)
        logs[os.path.basename(path)] = read_ubx_pvt(path)
        write_buster(os.path.join(out, os.path.basename(path)[:-4] + ".csv"), logs[os.path.basename(path)])
    rows = np.concatenate(list(logs.values()))
    lat0, lon0 = np.median(rows[:, 1]), np.median(rows[:, 2])
    e, n = east_north(rows[:, 1], rows[:, 2], lat0, lon0)
    pos = dict(
        lat_deg=float(lat0), lon_deg=float(lon0), height_m=float(np.median(rows[:, 3])),
        epochs=len(rows), from_utc=float(rows[0, 0]), to_utc=float(rows[-1, 0]),
        spread_east_m=float(np.std(e)), spread_north_m=float(np.std(n)),
        per_log={k: dict(epochs=len(v), median_east_m=float(np.median(east_north(v[:, 1], v[:, 2], lat0, lon0)[0])),
                         median_north_m=float(np.median(east_north(v[:, 1], v[:, 2], lat0, lon0)[1])))
                 for k, v in logs.items()},
        note="Median of the standalone fixes while the receiver stood at the cameras, about 45 cm behind "
             "them. Standalone: expect a bias of up to 1-2 m; post-processing the .ubx files removes it. "
             "Buster's later logs come from the same receiver, so much of that bias is common to both.")
    with open(os.path.join(out, "position.json"), "w") as f:
        json.dump(pos, f, indent=2)
    return pos


def camera_window(args, name):
    info = json.load(open(os.path.join(args.data, "recordings", name + "_info.json")))
    return info["start_system_time_us"] / 1e6, info["stop_system_time_us"] / 1e6


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="data_collection folder")
    ap.add_argument("--out", required=True, help="output folder")
    ap.add_argument("--experiments", nargs="+", default=list(EXPERIMENTS), choices=list(EXPERIMENTS))
    args = ap.parse_args()
    args.data, args.out = os.path.expanduser(args.data), os.path.expanduser(args.out)
    os.makedirs(args.out, exist_ok=True)

    cam_pos = camera_position(args)
    print(f"camera position: {cam_pos['lat_deg']:.7f} {cam_pos['lon_deg']:.7f}, {cam_pos['epochs']} epochs, "
          f"spread {cam_pos['spread_east_m']:.2f} m E, {cam_pos['spread_north_m']:.2f} m N")

    results = {}
    for name in args.experiments:
        spec = EXPERIMENTS[name]
        out = os.path.join(args.out, name)
        os.makedirs(out, exist_ok=True)
        ubx = find_ubx(args.data, spec["buster"])
        shutil.copy(ubx, os.path.join(out, "buster.ubx"))
        buster = read_ubx_pvt(ubx)
        write_buster(os.path.join(out, "buster.csv"), buster)
        cam_start, cam_stop = camera_window(args, spec["camera"])
        info = dict(experiment=name, note=spec["note"], camera_recording=spec["camera"],
                    camera_start_system_s=cam_start, camera_stop_system_s=cam_stop,
                    buster_log=os.path.basename(ubx), buster_utc=[float(buster[0, 0]), float(buster[-1, 0])],
                    observer=spec["observer"], bag=spec["bag"])

        if spec["bag"]:
            bag = glob.glob(os.path.join(args.data, "milliampere", spec["bag"], "*.mcap"))[0]
            print(f"{name}: reading {bag} ...", flush=True)
            fix, heading, imu, lag = read_bag(bag)
            write_csv(os.path.join(out, "milliampere_fix.csv"),
                      ["t_utc_s", "lat_deg", "lon_deg", "height_m", "status", "std_h_m"], fix,
                      ["%.3f", "%.9f", "%.9f", "%.3f", "%d", "%.4f"])
            write_csv(os.path.join(out, "milliampere_heading.csv"), ["t_utc_s", "heading_deg"], heading,
                      ["%.3f", "%.3f"])
            write_csv(os.path.join(out, "milliampere_imu.csv"),
                      ["t_utc_s", "gyro_x", "gyro_y", "gyro_z", "acc_x", "acc_y", "acc_z", "qx", "qy", "qz", "qw"],
                      imu, ["%.4f"] + ["%.6f"] * 10)
            rel = relative(buster, fix, heading)
            info.update(bag_utc=[float(fix[0, 0]), float(fix[-1, 0])], bag_stamp_latency_s=float(lag),
                        rtk_share=float(np.mean(fix[:, 4] == 2)),
                        start_difference_s=float(fix[0, 0] - cam_start))
        else:
            rel = relative(buster, fixed=(cam_pos["lat_deg"], cam_pos["lon_deg"]))
            info.update(start_difference_s=float(buster[0, 0] - cam_start))
        write_csv(os.path.join(out, "relative.csv"),
                  ["t_utc_s", "east_m", "north_m", "range_m", "bearing_deg", "rel_bearing_deg"], rel,
                  ["%.3f", "%.3f", "%.3f", "%.3f", "%.2f", "%.2f"])
        results[name] = (info, rel)

    # Coarse camera clock offset: the bag and the cameras were started by hand at about the same
    # time, so take the median of the bag start differences (buster logs started less consistently).
    diffs = [i["start_difference_s"] for i, _ in results.values() if i["bag"]]
    offset = float(np.median(diffs)) if diffs else None
    for name, (info, rel) in results.items():
        info.update(clock_offset_s=offset, clock_offset_note=(
            f"real UTC = camera system time + clock_offset_s. Median of the bag start differences "
            f"{[round(d) for d in diffs]}; good to about +-30 s, find the exact value from the data."))
        if offset is not None:
            t0, t1 = info["camera_start_system_s"] + offset, info["camera_stop_system_s"] + offset
            inside = (rel[:, 0] >= t0) & (rel[:, 0] <= t1)
            info.update(camera_utc_estimate=[t0, t1])
            if inside.any():
                info.update(range_during_camera_m=[float(rel[inside, 3].min()), float(rel[inside, 3].max())])
        with open(os.path.join(args.out, name, "info.json"), "w") as f:
            json.dump(info, f, indent=2)
        print(f"{name}: {len(rel)} buster epochs with observer, range {rel[:, 3].min():.1f}-{rel[:, 3].max():.1f} m, "
              f"during camera (coarse) {info.get('range_during_camera_m')}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(len(results), 1, figsize=(8, 2.2 * len(results)), squeeze=False)
    for ax, (name, (info, rel)) in zip(axes[:, 0], results.items()):
        t0 = info.get("camera_utc_estimate", [rel[0, 0]])[0]
        ax.plot(rel[:, 0] - t0, rel[:, 3], ".-", ms=3)
        if "camera_utc_estimate" in info:
            ax.axvspan(0, info["camera_utc_estimate"][1] - t0, color="0.9", label="camera recording (coarse)")
        ax.set_ylabel("range [m]")
        ax.set_title(f"{name}: {info['note']}", fontsize=8, loc="left")
        ax.grid(alpha=0.3)
    if "camera_utc_estimate" in info:
        axes[0, 0].legend(fontsize=7)
    axes[-1, 0].set_xlabel("time from camera start (coarse) [s]")
    fig.tight_layout()
    fig.savefig(os.path.join(args.out, "overview.png"), dpi=130)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
