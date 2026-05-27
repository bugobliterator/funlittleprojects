# `scanner` — Serial barcode-command CLI

**Date:** 2026-05-27
**Status:** Approved design
**Reference:** Honeywell N36XX Decoded Engine User's Guide (Rev A2), Chapter 10 "Serial Programming Commands"

## Purpose

A Python CLI for talking to a Honeywell N36XX decoded scan engine over an RS232
serial line. It sends raw menu/query/trigger commands using Honeywell's
menu-command protocol, parses the device's `ACK`/`ENQ`/`NAK` responses, and can
stream decoded barcode data back from the scanner.

The tool is a **raw passthrough**: the user supplies the menu mnemonic
(e.g. `CBRENA1`) and the tool handles framing, transport, and response parsing.
This works for every command in the datasheet without hardcoding a command
table.

## Protocol facts (from the datasheet)

Menu command syntax:

```
Prefix  Tag SubTag {Data} [, SubTag {Data}] [; Tag SubTag {Data}] ...  Storage
```

- **Prefix** — `SYN M CR` = ASCII `22, 77, 13` = bytes `\x16 \x4D \x0D`.
- **Tag / SubTag / Data** — supplied together by the user as one mnemonic
  string (e.g. `CBRENA1` = Tag `CBR` + SubTag `ENA` + Data `1`).
- **Storage** — a single trailing char: `!` = volatile table (lost on power
  cycle), `.` = non-volatile table (persists).
- **Query chars** appended in place of Data: `?` current value, `^` default
  value, `*` range of values.
- **Concatenation** — multiple commands in one frame: `,` separates commands
  sharing a Tag; `;` separates commands with a new Tag.

Responses — the device echoes the command back with a status byte inserted
**directly before each punctuation mark** (`.`, `!`, `,`, `;`):

- `ACK` = `\x06` — good command, processed.
- `ENQ` = `\x05` — invalid Tag or SubTag.
- `NAK` = `\x15` — valid command, Data out of allowable range.

Datasheet example — `cbr?.` returns:
```
CBRENA1[ACK],SSX0[ACK],CK20[ACK],CCT1[ACK],MIN2[ACK],MAX60[ACK],DFT[ACK].
```
(`[ACK]` denotes the non-displayable `\x06` byte.)

Trigger commands:
- Activate scan: `SYN T CR` = `\x16 \x54 \x0D`.
- Deactivate scan: `SYN U CR` = `\x16 \x55 \x0D`.
- Requires the engine to be in **Manual Trigger Mode** first (see README caveat).

Default RS232 settings: **115200 baud, 8 data bits, no parity, 1 stop bit (8N1)**.

## Architecture

Layered, with a pure protocol core isolated from I/O so it can be tested hard
against the datasheet examples without any hardware.

```
scanner-cli/
├── pyproject.toml          # deps: pyserial, click; dev: pytest. Python >= 3.10
├── README.md
├── src/scanner/
│   ├── __init__.py
│   ├── protocol.py         # pure: frame building + response parsing (no I/O)
│   ├── transport.py        # pyserial wrapper + port enumeration
│   └── cli.py              # click commands; main() entry point
└── tests/
    ├── test_protocol.py    # datasheet-derived cases, no hardware
    └── test_transport.py   # uses pyserial loop:// loopback
```

Console entry point: `scanner = "scanner.cli:main"`.

### `protocol.py` — pure, no I/O

Constants:

```python
PREFIX     = b"\x16M\r"     # SYN M CR
ACTIVATE   = b"\x16T\r"     # SYN T CR
DEACTIVATE = b"\x16U\r"     # SYN U CR

ACK = 0x06
ENQ = 0x05
NAK = 0x15
```

Enums:

- `Storage`: `VOLATILE = "!"`, `NONVOLATILE = "."`
- `Query`: `CURRENT = "?"`, `DEFAULT = "^"`, `RANGE = "*"`
- `Status`: `ACK`, `ENQ`, `NAK`

Functions:

- `build_menu_command(mnemonic: str, storage: Storage = VOLATILE) -> bytes`
  Returns `PREFIX + mnemonic.encode("ascii") + storage.value.encode()`.
  Example: `build_menu_command("CBRENA1")` → `b"\x16M\rCBRENA1!"`.

- `build_query(tag_subtag: str, kind: Query = CURRENT, storage: Storage = NONVOLATILE) -> bytes`
  Example: `build_query("CBRENA", Query.CURRENT)` → `b"\x16M\rCBRENA?."`
  (queries default to the `.` terminator to match the datasheet examples).

- `parse_response(raw: bytes) -> list[Response]`
  `Response` is a dataclass `(payload: str, status: Status)`. Scans `raw`,
  accumulating payload bytes until a status byte (`\x06`/`\x05`/`\x15`) is hit,
  records `(payload, status)`, skips the following punctuation char
  (`, ; . !`) if present, and continues. Reproduces the `cbr?.` example as 7
  `Response` entries.

### `transport.py` — only hardware-touching layer

- `class SerialTransport` — constructed with
  `(port, baud=115200, bytesize=8, parity="N", stopbits=1, timeout=2.0)`;
  usable as a context manager (`with SerialTransport(...) as t:`).
  - `send(data: bytes) -> None`
  - `read_response(quiet: float = 0.2, timeout: float = 2.0) -> bytes` —
    reads bytes until the line stays quiet for `quiet` seconds or `timeout`
    elapses. Tolerant of varied ACK/ENQ/NAK response shapes.
  - `read_scans() -> Iterator[str]` — generator for listen mode; yields decoded
    barcode strings, splitting the incoming stream on CR/LF.
- `list_ports() -> list[ListPortInfo]` via `serial.tools.list_ports`.
- Tests drive it through pyserial's built-in `serial_for_url("loop://")`
  loopback, so no scanner is required.

### `cli.py` — Click commands

Group-level options:
`--port/-p` (required for commands that talk to hardware), `--baud/-b`
(default 115200), `--bytesize` (8), `--parity` (N), `--stopbits` (1),
`--timeout` (2.0), `--verbose/-v` (print TX/RX bytes as hex).

| Command | Behavior |
|---|---|
| `scanner ports` | List available serial ports. Does not need `--port`. |
| `scanner send MNEMONIC [--persist]` | Build menu command (`!` volatile, or `.` with `--persist`), send, read + parse response, print status. |
| `scanner query TAGSUBTAG [--kind current\|default\|range]` | Build + send query (default `current`/`?`), print parsed payload(s). |
| `scanner trigger` | Send `SYN T CR`. |
| `scanner untrigger` | Send `SYN U CR`. |
| `scanner listen [--seconds N]` | Activate trigger, stream decoded barcodes until Ctrl-C or `N` seconds, then deactivate. |
| `scanner repl` | Interactive session: each typed line is a mnemonic (auto-wrapped, sent, parsed). Meta-commands: `:trigger`, `:untrigger`, `:listen`, `:quit`. |

## Error handling & exit codes

| Code | Meaning |
|---|---|
| 0 | `ACK` — command processed. |
| 1 | `NAK` — Data out of allowable range. |
| 2 | `ENQ` — invalid Tag or SubTag. |
| 3 | No response / garbled response (prints received bytes as hex). |
| 4 | Connection error (port missing, permission denied, etc.). |

`NAK` and `ENQ` results print the datasheet's plain-English meaning. Connection
errors print a clear message (on macOS the port is typically
`/dev/cu.usbserial-*` or `/dev/tty.usbserial-*`).

## Testing

- **`test_protocol.py`** (pure, fast, no hardware):
  - `build_menu_command("CBRENA1") == b"\x16M\rCBRENA1!"`
  - `build_query("CBRENA", Query.CURRENT) == b"\x16M\rCBRENA?."`
  - `parse_response` reproduces the datasheet `cbr?.` multi-response example
    (7 `Response`s, all `ACK`, payloads `CBRENA1`, `SSX0`, `CK20`, `CCT1`,
    `MIN2`, `MAX60`, `DFT`).
  - `ENQ` and `NAK` single-response cases.
  - Trigger/deactivate byte constants.
- **`test_transport.py`**: exercise `send` / `read_response` over
  `serial_for_url("loop://")`.
- **`test_cli.py`** (optional): Click `CliRunner` with a fake transport;
  assert exit codes and output for `ACK` / `NAK` / `ENQ`.

## Dependencies

- Runtime: `pyserial`, `click`.
- Dev: `pytest`.
- Python: >= 3.10.

## Decisions / caveats

- `send` defaults to **volatile `!`** storage (safe; reverts on power cycle).
  Use `--persist` to write the non-volatile `.` table.
- `trigger` / `listen` require the engine to be in **Manual Trigger Mode**
  (`TRGMOD` command). The tool does not auto-set this; the README documents it.
- Raw passthrough only — no curated per-setting subcommands. Every datasheet
  command is reachable via `send` / `query`.
