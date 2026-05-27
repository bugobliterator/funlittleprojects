# scanner

A small CLI for sending Honeywell N36XX barcode-engine commands over serial.
It frames raw menu/query/trigger commands (Honeywell's `SYN M CR` protocol),
parses `ACK`/`ENQ`/`NAK` responses, and can stream decoded barcodes.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

This installs a `scanner` command.

## Usage

The engine must be set to an **RS232 interface** (scan the `PAP232` Plug-and-Play
code or send `PAP232`). Default serial settings: **115200 baud, 8N1**.

```bash
# List serial ports
scanner ports

# Send a menu command (volatile by default)
scanner -p /dev/cu.usbserial-XXXX send CBRENA1

# Persist to the non-volatile table
scanner -p /dev/cu.usbserial-XXXX send CBRENA1 --persist

# Query a setting (current value)
scanner -p /dev/cu.usbserial-XXXX query CBRENA
scanner -p /dev/cu.usbserial-XXXX query CBRENA --kind range
scanner -p /dev/cu.usbserial-XXXX query CBRENA --kind default

# Trigger / read barcodes (see caveat below)
scanner -p /dev/cu.usbserial-XXXX trigger
scanner -p /dev/cu.usbserial-XXXX untrigger
scanner -p /dev/cu.usbserial-XXXX listen --seconds 10

# Interactive session
scanner -p /dev/cu.usbserial-XXXX repl
```

Add `-v` to print the exact TX/RX bytes as hex (useful for debugging framing).

### Mnemonics

A mnemonic is the Tag + SubTag + Data string from the datasheet's command
tables, e.g. `CBRENA1` (Codabar enable = on), `232BAD9` (RS232 baud rate code),
`DEFALT` (activate custom defaults). The tool adds the `SYN M CR` prefix and the
storage terminator (`!` volatile / `.` non-volatile) for you.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | ACK — command processed |
| 1 | NAK — data out of allowable range |
| 2 | ENQ — invalid Tag or SubTag (also: CLI usage error) |
| 3 | No / garbled response |
| 4 | Connection error |

## Caveat: trigger and listen

`trigger` / `listen` only work when the engine is in **Manual Trigger Mode**.
Put it there first, e.g.:

```bash
scanner -p /dev/cu.usbserial-XXXX send TRGMOD0   # Manual Trigger - Normal
```

(See the N36XX User's Guide "Trigger Modes" section for the exact mnemonic for
your firmware.)

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```
