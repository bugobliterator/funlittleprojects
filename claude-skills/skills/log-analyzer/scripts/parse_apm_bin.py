#!/usr/bin/env python3
"""
Parse an ArduPilot dataflash .bin log into JSON.

Usage:
  parse_apm_bin.py INPUT.bin OUTPUT.json
                   [--types T1,T2,...] [--subsample-types T1,T2,...]
                   [--subsample-hz HZ] [--all]

Default: keep GPS / status / event / version / mode messages at full rate;
subsample high-rate sensor types (IMU, ATT, BARO, MAG, VIBE, XKF*, BAT, RC*)
to 1 Hz; skip everything else.

Pass --all to include every message at full rate (warning: large output).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

try:
    from pymavlink import mavutil
except ImportError:
    sys.exit(
        "ERROR: pymavlink is required. Install with:\n"
        "  pip install --break-system-packages pymavlink"
    )

# ArduPilot boot logs typically include a MSG line of the form
# "<BoardName> <hex16/8> <hex8> <hex8>" — e.g. "CubeOrange 003D0032 33325116 31323432".
# Extract the leading board-name token from any MSG that matches.
BOARD_MSG_RE = re.compile(
    r"^([A-Za-z][\w+\-]*)\s+[0-9A-Fa-f]{6,16}\s+[0-9A-Fa-f]{6,16}\s+[0-9A-Fa-f]{6,16}\s*$"
)


def detect_boardname(msg_texts: list) -> str:
    """Return the boardname from a MSG line if one matches BOARD_MSG_RE; else ''."""
    for s in msg_texts:
        if not isinstance(s, str):
            continue
        m = BOARD_MSG_RE.match(s.strip())
        if m:
            return m.group(1)
    return ""


# Event / status / version / GPS messages — kept at full rate.
DEFAULT_FULL_TYPES = {
    "GPS", "GPS2", "GPA", "GPA2", "POS", "ORGN",
    "MSG", "VER", "MODE", "STAT",
    "EV", "ARM", "CMD", "CMDI",
    "FNCE", "FAIL", "ERR", "PARM",
    "RFND", "TERR",
}

# High-rate sensor / state messages — subsampled.
DEFAULT_SUBSAMPLE_TYPES = {
    "IMU", "IMU2", "IMU3",
    "ATT", "BARO", "BAR2",
    "MAG", "MAG2", "MAG3",
    "VIBE", "DCM", "EAHR",
    "XKF1", "XKF2", "XKF3", "XKF4", "XKQ", "XKFS", "XKFD",
    "RCIN", "RCOU", "BAT", "BAT2", "POWR",
    "MCU", "FTN2", "ISBD",
}


def parse_log(path: str, types_full: set, types_sub: set, subsample_hz: float) -> dict:
    m = mavutil.mavlink_connection(path)
    type_counts: dict[str, int] = {}
    msgs_out: list = []
    last_sub_us: dict[str, int] = {}
    sub_period_us = int(1e6 / subsample_hz) if subsample_hz > 0 else 0
    versions: list = []
    msg_text: list = []
    first_us = None
    last_us = None
    bad_data = 0

    while True:
        msg = m.recv_match()
        if msg is None:
            break
        t = msg.get_type()
        if t == "BAD_DATA":
            bad_data += 1
            continue
        type_counts[t] = type_counts.get(t, 0) + 1
        d = msg.to_dict()
        tu = d.get("TimeUS")
        if tu is not None:
            if first_us is None:
                first_us = tu
            last_us = tu

        if t in types_full:
            msgs_out.append(d)
            if t == "VER":
                versions.append(d)
            elif t == "MSG":
                msg_text.append(d.get("Message", ""))
        elif t in types_sub:
            if tu is None or sub_period_us == 0:
                msgs_out.append(d)
            else:
                last = last_sub_us.get(t, -10**18)
                if tu - last >= sub_period_us:
                    msgs_out.append(d)
                    last_sub_us[t] = tu
        # else: skip

    duration_s = (
        (last_us - first_us) / 1e6
        if (first_us is not None and last_us is not None)
        else 0
    )
    fw = ""
    if versions:
        v = versions[-1]
        fw = v.get("FWS", "")
    # boardname is detected from MSG strings (a VER.BU value is a build number, not a name)
    boardname = detect_boardname(msg_text)

    return {
        "file": {
            "path": str(path),
            "size_bytes": os.path.getsize(path),
            "parsed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "format": "ardupilot_dataflash_bin",
        },
        "summary": {
            "firmware_version_string": fw,
            "boardname": boardname,
            "first_msg_text": msg_text[:30],
            "messages_total_parsed": sum(type_counts.values()),
            "messages_in_output": len(msgs_out),
            "bad_data_blocks": bad_data,
            "message_type_counts": dict(
                sorted(type_counts.items(), key=lambda x: -x[1])
            ),
            "duration_seconds": duration_s,
            "subsample_hz": subsample_hz,
            "kept_full_rate_types": sorted(types_full),
            "kept_subsampled_types": sorted(types_sub),
        },
        "messages": msgs_out,
    }


def parse_log_all(path: str) -> dict:
    m = mavutil.mavlink_connection(path)
    type_counts: dict[str, int] = {}
    msgs_out: list = []
    msg_text: list = []
    first_us = None
    last_us = None
    bad_data = 0
    fw = ""

    while True:
        msg = m.recv_match()
        if msg is None:
            break
        t = msg.get_type()
        if t == "BAD_DATA":
            bad_data += 1
            continue
        type_counts[t] = type_counts.get(t, 0) + 1
        d = msg.to_dict()
        tu = d.get("TimeUS")
        if tu is not None:
            if first_us is None:
                first_us = tu
            last_us = tu
        msgs_out.append(d)
        if t == "VER":
            fw = d.get("FWS", fw)
        elif t == "MSG":
            msg_text.append(d.get("Message", ""))

    boardname = detect_boardname(msg_text)

    duration_s = (
        (last_us - first_us) / 1e6
        if (first_us is not None and last_us is not None)
        else 0
    )
    return {
        "file": {
            "path": str(path),
            "size_bytes": os.path.getsize(path),
            "parsed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "format": "ardupilot_dataflash_bin",
        },
        "summary": {
            "firmware_version_string": fw,
            "boardname": boardname,
            "messages_total_parsed": sum(type_counts.values()),
            "messages_in_output": len(msgs_out),
            "bad_data_blocks": bad_data,
            "message_type_counts": dict(
                sorted(type_counts.items(), key=lambda x: -x[1])
            ),
            "duration_seconds": duration_s,
            "subsample_hz": 0.0,
            "mode": "all",
        },
        "messages": msgs_out,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="ArduPilot .bin -> JSON")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument(
        "--types",
        default=None,
        help="Comma-separated message types to include at full rate. "
             "Default = built-in event/status/GPS set.",
    )
    p.add_argument(
        "--subsample-types",
        default=None,
        help="Comma-separated types to subsample. "
             "Default = high-rate sensor types.",
    )
    p.add_argument(
        "--subsample-hz",
        type=float,
        default=1.0,
        help="Subsample rate for high-rate types in Hz. Default 1.0. "
             "Use 0 to keep all samples of those types.",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Include ALL message types at full rate (large output).",
    )
    args = p.parse_args()

    if args.all:
        out = parse_log_all(args.input)
    else:
        types_full = (
            set(args.types.split(","))
            if args.types
            else set(DEFAULT_FULL_TYPES)
        )
        types_sub = (
            set(args.subsample_types.split(","))
            if args.subsample_types
            else set(DEFAULT_SUBSAMPLE_TYPES)
        )
        out = parse_log(args.input, types_full, types_sub, args.subsample_hz)

    with open(args.output, "w") as f:
        json.dump(out, f, default=str)

    print(
        f"Wrote {args.output}: "
        f"{out['summary']['messages_in_output']} kept / "
        f"{out['summary']['messages_total_parsed']} parsed "
        f"({out['summary']['duration_seconds']:.1f}s of log)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
