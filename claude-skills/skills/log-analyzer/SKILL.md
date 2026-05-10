---
name: log-analyzer
description: Convert ArduPilot dataflash logs (.bin) and u-blox UBX/NMEA captures (.ubx) into structured JSON for downstream analysis and plotting. Auto-files outputs into the active customer-support ticket's logs/ folder when one is identifiable. Use this skill whenever the user asks you to analyze, look at, parse, extract, or examine a flight log, dataflash log, .bin file, .ubx file, GPS log, ublox log, telemetry log, or any drone-flight-data forensics — even when the user just says "look at this log", "what's in this file", "analyse the log for the ticket", or "convert this to JSON". This skill is essential for CubePilot customer-support tickets where logs are attached as evidence; without it Claude tends to invent or skim, which violates the project's strict "never generate information not provided by the user" rule.
---

# Log Analyzer

Convert flight logs to JSON. Then read the JSON to answer questions about what's in the log.

The point of this skill is to put a clean line between **observation** (parsing the binary, extracting fields) and **interpretation** (Claude reading the JSON and reasoning about it). Observation runs through deterministic scripts. Interpretation happens after, against the JSON.

## When to trigger

Trigger on any request that involves looking at a `.bin` or `.ubx` log file. Specifically:

- "analyse the log for this ticket"
- "what does this dataflash log show"
- "parse this .ubx file"
- "did the GPS lose satellites in flight"
- "extract the firmware version from this log"
- "convert this log to JSON"
- attached files with `.bin` or `.ubx` extension when the user is asking anything about them

If the request is just "where did the user upload this" or "rename this file", do not trigger — that's a file-management task, not a log analysis task.

## Hard rule on output

Anchor every claim about the log in a value you can point to in the JSON. Do not summarize from training knowledge or extrapolate beyond what the parsed messages literally say. If a user asks "why did the GPS drop", the right answer shape is "the JSON shows NSats went 32 → 14 between iTOW=X and iTOW=X+200ms; pDOP rose from 0.93 to 1.41 in the same window" — not "GPS modules typically drop sats due to RF interference".

If the user asks something the JSON does not contain the data for, say so. Suggest a re-parse with `--all` or `--include-rxm` if the missing data could be in the source file.

## Workflow

### 1. Identify the active ticket folder (if any)

If the working directory is `/Users/sidbh/Documents/Customer Support/Customer Support` (or the user is talking about a `CS-YYYY-NNN-...` ticket), the JSON output should land in `<ticket>/logs/`. Look for the relevant ticket folder — it usually has the file already copied in `<ticket>/logs/`.

If no ticket context is identifiable, write the JSON next to the input file (same directory, same basename, `.json` extension).

### 2. Run the right parser

```bash
# ArduPilot dataflash → JSON
python3 <skill-dir>/scripts/parse_apm_bin.py <input>.bin <output>.json

# u-blox UBX (or mixed UBX+NMEA) → JSON
python3 <skill-dir>/scripts/parse_ubx.py <input>.ubx <output>.json
```

Both scripts produce a single JSON object with `file`, `summary`, and `messages` keys (see "Output structure" below).

Defaults are tuned for support-ticket-sized logs (a few minutes to an hour, 10–50 MB):

- `parse_apm_bin.py` keeps GPS / status / event / version messages at full rate; subsamples high-rate sensor types (IMU, ATT, BARO, MAG, VIBE, XKF*, BAT, RC*) to 1 Hz; skips other types entirely.
- `parse_ubx.py` decodes MON-VER, NAV-PVT, NAV-DOP into structured fields; logs every UBX message header with class/id; captures NMEA sentence type + comma-separated fields; skips RXM-RAWX / RXM-SFRBX payload bodies unless `--include-rxm` is passed.

If the user wants the full message stream, pass:

```bash
python3 .../parse_apm_bin.py input.bin output.json --all          # ALL types, full rate (large)
python3 .../parse_apm_bin.py input.bin output.json --types GPS,GPS2,IMU --subsample-hz 0   # specific types only
python3 .../parse_ubx.py input.ubx output.json --include-rxm      # include raw GNSS measurements
```

### 3. Read the JSON and answer the user's question

Use `python -c` or `jq` to slice into the JSON. Don't paste the full file into context. Useful patterns:

```bash
# Top-of-file: file metadata, firmware string, message-type histogram
python3 -c "import json; d=json.load(open('out.json')); print(json.dumps(d['summary'], indent=2)[:2000])"

# All GPS messages (small)
python3 -c "import json; d=json.load(open('out.json')); [print(m) for m in d['messages'] if m.get('mavpackettype')=='GPS'][:50]"

# Find sat-count drops > N between adjacent samples
python3 -c "
import json
d = json.load(open('out.json'))
gps = [m for m in d['messages'] if m.get('mavpackettype')=='GPS']
for a,b in zip(gps, gps[1:]):
    if a['NSats']-b['NSats'] >= 5:
        print(f'TimeUS={b[\"TimeUS\"]} {a[\"NSats\"]} -> {b[\"NSats\"]}')
"
```

Always cite the iTOW / TimeUS / message index of any value you quote, so the user can verify it themselves.

### 4. Update ticket files (when a ticket is in play)

If the JSON went into a ticket's `logs/` folder, update or create `<ticket>/logs/README.md` to record:
- Filename of the source log
- Filename of the JSON
- Firmware version string (from `summary.firmware_version_string` or `summary.mon_ver`)
- Vehicle/board info from MSG entries (look for "ArduCopter V...", "CubeOrange", "IFT...", "Frame:" strings)
- Any anomalies actually visible in the JSON (do not invent — only what the data literally shows)

This keeps the audit trail intact per the project's CLAUDE.md.

## Output structure

Both parsers produce JSON in this shape:

```json
{
  "file": {
    "path": "/full/path/to/input.bin",
    "size_bytes": 12394496,
    "parsed_at": "2026-05-07T04:00:00Z",
    "format": "ardupilot_dataflash_bin"
  },
  "summary": {
    // Parser-specific fields. Always includes message_type_counts (or class_id_counts for UBX).
    // For .bin: firmware_version_string, boardname, first_msg_text, duration_seconds.
    // For .ubx: ubx_messages_total, nmea_sentences_total, mon_ver (decoded swVersion/hwVersion/extensions).
  },
  "messages": [
    // One object per kept message. Schema follows pymavlink's to_dict() for .bin
    // or {type, class, id, name, ...decoded_fields} for .ubx UBX, and
    // {type, talker, sentence, fields} for NMEA.
  ]
}
```

JSON files for a 45 MB .bin typically come out 3–8 MB at default settings. With `--all`, expect 40–120 MB.

## Dependencies

- `pymavlink` — install with `pip install --break-system-packages pymavlink` if not present.
- Python 3 standard library is enough for `parse_ubx.py`.

## Failure modes and what to do

- **Parser returns 0 messages on a .bin** — file is probably corrupt or not a dataflash log. Run `head -c 16 input.bin | xxd` and check for the magic header `a3 95 ...YFMT...`. If it's missing, the file is something else (tlog, ULog, raw TCP capture).
- **UBX parser shows almost no UBX messages and lots of NMEA** — the source was configured NMEA-only. You can still extract sat counts and fix status from `$GxGGA` / `$GxGSV` / `$GxGSA` sentences via the NMEA fields, but raw GNSS measurements (RXM-RAWX) are not in the file. Tell the user.
- **Truncated payload errors** — a message header reports a length that runs past EOF. Parser stops there; you still get everything before. Note this in the JSON's `summary` if it shows up (today the parsers silently stop; that's a known limitation).
- **MON-VER missing on a .ubx file** — the receiver was never queried for version. Cannot identify firmware from this file alone; ask the user.

## Bundled scripts

- [`scripts/parse_apm_bin.py`](scripts/parse_apm_bin.py) — ArduPilot dataflash → JSON
- [`scripts/parse_ubx.py`](scripts/parse_ubx.py) — u-blox UBX/NMEA → JSON
