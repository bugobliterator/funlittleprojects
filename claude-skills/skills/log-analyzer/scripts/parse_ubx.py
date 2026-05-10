#!/usr/bin/env python3
"""
Parse a u-blox UBX/NMEA capture (.ubx) into JSON.

Handles mixed UBX + NMEA streams (common when captured via TCP from u-center
or directly from a u-blox receiver).

Usage:
  parse_ubx.py INPUT.ubx OUTPUT.json [--include-rxm]

Output:
  Single JSON object with file/summary/messages keys. UBX messages get a
  named entry (e.g. "NAV-PVT"); NAV-PVT/NAV-DOP/MON-VER bodies are decoded
  to structured fields. Other UBX bodies stay as headers only.
  RXM-RAWX / RXM-SFRBX bodies are skipped unless --include-rxm.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import time

# (class, id) -> name mapping for the most common ublox messages we see
# in customer-attached captures.
UBX_NAME = {
    (0x01, 0x07): "NAV-PVT",
    (0x01, 0x04): "NAV-DOP",
    (0x01, 0x35): "NAV-SAT",
    (0x01, 0x12): "NAV-VELNED",
    (0x01, 0x20): "NAV-TIMEGPS",
    (0x01, 0x21): "NAV-TIMEUTC",
    (0x05, 0x01): "ACK-ACK",
    (0x05, 0x00): "ACK-NAK",
    (0x06, 0x8B): "CFG-VALGET",
    (0x0A, 0x04): "MON-VER",
    (0x0A, 0x09): "MON-HW",
    (0x0A, 0x0B): "MON-HW2",
    (0x0A, 0x31): "MON-SPAN",
    (0x02, 0x15): "RXM-RAWX",
    (0x02, 0x13): "RXM-SFRBX",
}

NMEA_RE = re.compile(rb"\$([A-Z]{2})([A-Z]{3}),([^\r\n*]*)\*[0-9A-Fa-f]{2}")


def decode_mon_ver(payload: bytes) -> dict:
    sw = payload[0:30].split(b"\x00", 1)[0].decode("ascii", "replace")
    hw = payload[30:40].split(b"\x00", 1)[0].decode("ascii", "replace")
    exts = []
    i = 40
    while i + 30 <= len(payload):
        e = payload[i:i + 30].split(b"\x00", 1)[0].decode("ascii", "replace")
        if e:
            exts.append(e)
        i += 30
    return {"swVersion": sw, "hwVersion": hw, "extensions": exts}


def decode_nav_pvt(payload: bytes) -> dict | None:
    if len(payload) < 92:
        return None
    iTOW = struct.unpack("<I", payload[0:4])[0]
    year, month, day, hour, minute, sec = struct.unpack("<HBBBBB", payload[4:11])
    valid = payload[11]
    tAcc = struct.unpack("<I", payload[12:16])[0]
    nano = struct.unpack("<i", payload[16:20])[0]
    fixType = payload[20]
    flags = payload[21]
    flags2 = payload[22]
    numSV = payload[23]
    lon, lat, height, hMSL = struct.unpack("<iiii", payload[24:40])
    hAcc, vAcc = struct.unpack("<II", payload[40:48])
    velN, velE, velD = struct.unpack("<iii", payload[48:60])
    gSpeed = struct.unpack("<i", payload[60:64])[0]
    headMot = struct.unpack("<i", payload[64:68])[0]
    sAcc = struct.unpack("<I", payload[68:72])[0]
    headAcc = struct.unpack("<I", payload[72:76])[0]
    pDOP = struct.unpack("<H", payload[76:78])[0]
    return {
        "iTOW": iTOW,
        "year": year, "month": month, "day": day,
        "hour": hour, "min": minute, "sec": sec,
        "valid": valid, "tAcc": tAcc, "nano": nano,
        "fixType": fixType, "flags": flags, "flags2": flags2, "numSV": numSV,
        "lon_deg": lon * 1e-7, "lat_deg": lat * 1e-7,
        "height_mm": height, "hMSL_mm": hMSL,
        "hAcc_mm": hAcc, "vAcc_mm": vAcc,
        "velN_mm_s": velN, "velE_mm_s": velE, "velD_mm_s": velD,
        "gSpeed_mm_s": gSpeed, "headMot_1e5_deg": headMot,
        "sAcc_mm_s": sAcc, "headAcc_1e5_deg": headAcc,
        "pDOP_0_01": pDOP,
    }


def decode_nav_dop(payload: bytes) -> dict | None:
    if len(payload) < 18:
        return None
    iTOW, gDOP, pDOP, tDOP, vDOP, hDOP, nDOP, eDOP = struct.unpack(
        "<IHHHHHHH", payload[0:18]
    )
    return {
        "iTOW": iTOW,
        "gDOP_0_01": gDOP, "pDOP_0_01": pDOP, "tDOP_0_01": tDOP,
        "vDOP_0_01": vDOP, "hDOP_0_01": hDOP,
        "nDOP_0_01": nDOP, "eDOP_0_01": eDOP,
    }


def decode_ubx(cls: int, mid: int, payload: bytes) -> dict | None:
    if (cls, mid) == (0x0A, 0x04):
        return decode_mon_ver(payload)
    if (cls, mid) == (0x01, 0x07):
        return decode_nav_pvt(payload)
    if (cls, mid) == (0x01, 0x04):
        return decode_nav_dop(payload)
    return None


def parse_stream(data: bytes, include_rxm: bool) -> dict:
    out_msgs: list = []
    n_ubx = 0
    n_nmea = 0
    class_id_counts: dict[str, int] = {}
    mon_ver: list = []
    truncated = False

    i = 0
    L = len(data)

    while i < L:
        b = data[i]

        # UBX framing
        if b == 0xB5 and i + 1 < L and data[i + 1] == 0x62:
            if i + 8 > L:
                truncated = True
                break
            cls = data[i + 2]
            mid = data[i + 3]
            ln = struct.unpack("<H", data[i + 4:i + 6])[0]
            if i + 6 + ln + 2 > L:
                truncated = True
                break
            payload = data[i + 6:i + 6 + ln]

            n_ubx += 1
            key = f"{cls:02X}_{mid:02X}"
            class_id_counts[key] = class_id_counts.get(key, 0) + 1

            name = UBX_NAME.get((cls, mid), f"UNK-{cls:02X}-{mid:02X}")
            entry = {
                "type": "ubx",
                "class": f"{cls:02X}",
                "id": f"{mid:02X}",
                "name": name,
                "len": ln,
            }
            decoded = decode_ubx(cls, mid, payload)
            if decoded is not None:
                entry.update(decoded)
            if name == "MON-VER" and decoded is not None:
                mon_ver.append(decoded)

            # Drop RXM payload bodies unless requested — they're huge and
            # we only kept the header above anyway.
            is_rxm = (cls, mid) in {(0x02, 0x15), (0x02, 0x13)}
            if is_rxm and not include_rxm:
                pass  # already only have a header entry
            else:
                out_msgs.append(entry)

            i += 6 + ln + 2
            continue

        # NMEA framing
        if b == 0x24:  # '$'
            j = data.find(b"\n", i, min(L, i + 200))
            if j == -1:
                j = i + 1
            line = data[i:j].rstrip(b"\r")
            m = NMEA_RE.match(line)
            if m:
                talker = m.group(1).decode("ascii", "ignore")
                sentence = m.group(2).decode("ascii", "ignore")
                fields = m.group(3).decode("ascii", "ignore").split(",")
                out_msgs.append({
                    "type": "nmea",
                    "talker": talker,
                    "sentence": sentence,
                    "fields": fields,
                })
                n_nmea += 1
            i = j + 1
            continue

        i += 1

    return {
        "n_ubx": n_ubx,
        "n_nmea": n_nmea,
        "class_id_counts": dict(
            sorted(class_id_counts.items(), key=lambda x: -x[1])
        ),
        "mon_ver": mon_ver,
        "messages": out_msgs,
        "truncated_at_eof": truncated,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="u-blox UBX/NMEA -> JSON")
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument(
        "--include-rxm",
        action="store_true",
        help="Include RXM-RAWX / RXM-SFRBX message headers in output. "
             "(Bodies are not currently decoded — header-only.)",
    )
    args = p.parse_args()

    with open(args.input, "rb") as f:
        data = f.read()

    parsed = parse_stream(data, args.include_rxm)

    out = {
        "file": {
            "path": str(args.input),
            "size_bytes": os.path.getsize(args.input),
            "parsed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "format": "ublox_ubx_or_mixed",
        },
        "summary": {
            "ubx_messages_total": parsed["n_ubx"],
            "nmea_sentences_total": parsed["n_nmea"],
            "ubx_class_id_counts": parsed["class_id_counts"],
            "mon_ver": parsed["mon_ver"],
            "truncated_at_eof": parsed["truncated_at_eof"],
        },
        "messages": parsed["messages"],
    }
    with open(args.output, "w") as f:
        json.dump(out, f, default=str)

    print(
        f"Wrote {args.output}: "
        f"{parsed['n_ubx']} UBX msgs, {parsed['n_nmea']} NMEA sentences"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
