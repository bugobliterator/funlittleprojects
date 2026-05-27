# `scanner` Serial Barcode-Command CLI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python CLI (`scanner`) that sends Honeywell N36XX menu/query/trigger commands over an RS232 serial line, parses `ACK`/`ENQ`/`NAK` responses, and streams decoded barcodes.

**Architecture:** Three layers — `protocol.py` (pure framing + response parsing, no I/O), `transport.py` (the only `pyserial`-touching layer), `cli.py` (Click commands). The pure protocol core is tested against the datasheet examples without hardware; transport is tested over pyserial's `loop://` loopback; the CLI is tested with Click's `CliRunner` plus a fake transport.

**Tech Stack:** Python ≥3.10, `pyserial`, `click`, `pytest`. src-layout package installed editable into a local `.venv`.

**Spec:** `docs/superpowers/specs/2026-05-27-scanner-serial-cli-design.md`

**Protocol reference (datasheet):**
- Menu command frame: `PREFIX + mnemonic + storage`, `PREFIX = b"\x16M\r"` (SYN M CR).
- Storage terminator: `!` volatile, `.` non-volatile.
- Query char replaces Data: `?` current, `^` default, `*` range.
- Trigger: activate `b"\x16T\r"` (SYN T CR), deactivate `b"\x16U\r"` (SYN U CR).
- Response: device echoes payload with a status byte before each punctuation mark (`, ; . !`). Status bytes: `ACK=0x06`, `ENQ=0x05`, `NAK=0x15`.
- Multi-response example for `cbr?.`: `CBRENA1[ACK],SSX0[ACK],CK20[ACK],CCT1[ACK],MIN2[ACK],MAX60[ACK],DFT[ACK].`

---

## File Structure

```
scanner-cli/
├── pyproject.toml          # deps + console entry point `scanner`
├── README.md               # usage + Manual Trigger Mode caveat
├── .gitignore              # .venv/, __pycache__, etc.
├── src/scanner/
│   ├── __init__.py         # package marker + __version__
│   ├── protocol.py         # pure: enums, constants, build_*, parse_response
│   ├── transport.py        # SerialTransport, list_ports
│   └── cli.py              # Click group + commands + main()
└── tests/
    ├── test_protocol.py
    ├── test_transport.py
    └── test_cli.py
```

Responsibilities:
- **protocol.py** — turn a mnemonic into bytes; turn raw response bytes into `Response` objects. No imports of `serial`.
- **transport.py** — open/write/read a serial port; enumerate ports. No knowledge of command semantics.
- **cli.py** — argument parsing, wiring protocol↔transport, exit codes, user-facing output.

---

## Task 1: Project scaffold + tooling

**Files:**
- Create: `scanner-cli/pyproject.toml`
- Create: `scanner-cli/.gitignore`
- Create: `scanner-cli/src/scanner/__init__.py`
- Create: `scanner-cli/src/scanner/protocol.py` (empty placeholder)
- Create: `scanner-cli/src/scanner/transport.py` (empty placeholder)
- Create: `scanner-cli/src/scanner/cli.py` (minimal `main` so the entry point imports)
- Create: `scanner-cli/tests/__init__.py` (empty)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "scanner-cli"
version = "0.1.0"
description = "Send Honeywell N36XX barcode commands over serial."
requires-python = ">=3.10"
dependencies = [
    "pyserial>=3.5",
    "click>=8.1",
]

[project.scripts]
scanner = "scanner.cli:main"

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/scanner"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/
build/
dist/
```

- [ ] **Step 3: Create `src/scanner/__init__.py`**

```python
"""scanner -- send Honeywell N36XX barcode commands over serial."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Create placeholder modules**

`src/scanner/protocol.py`:
```python
"""Honeywell N36XX serial menu-command protocol: framing and response parsing."""
```

`src/scanner/transport.py`:
```python
"""Serial transport -- the only hardware-touching layer."""
```

`src/scanner/cli.py`:
```python
"""Command-line interface for the scanner tool."""

import click


@click.group()
def main() -> None:
    """Send Honeywell N36XX barcode commands over serial."""


if __name__ == "__main__":
    main()
```

`tests/__init__.py`: leave empty (create the empty file).

- [ ] **Step 5: Create venv and editable install**

Run:
```bash
cd scanner-cli
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```
Expected: install succeeds, ending with a line like `Successfully installed ... scanner-cli-0.1.0`.

- [ ] **Step 6: Verify import, entry point, and pytest**

Run:
```bash
cd scanner-cli
.venv/bin/python -c "import scanner; print(scanner.__version__)"
.venv/bin/scanner --help
.venv/bin/pytest -q
```
Expected: prints `0.1.0`; `--help` shows the group usage; pytest reports `no tests ran` (0 collected) and exits 0.

- [ ] **Step 7: Commit**

```bash
git add scanner-cli
git commit -m "scaffold scanner serial CLI project"
```

---

## Task 2: protocol.py — constants, enums, and command builders

**Files:**
- Modify: `scanner-cli/src/scanner/protocol.py`
- Test: `scanner-cli/tests/test_protocol.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_protocol.py`:
```python
from scanner.protocol import (
    PREFIX,
    ACTIVATE,
    DEACTIVATE,
    Storage,
    Query,
    build_menu_command,
    build_query,
)


def test_frame_constants():
    assert PREFIX == b"\x16M\r"        # SYN M CR
    assert ACTIVATE == b"\x16T\r"      # SYN T CR
    assert DEACTIVATE == b"\x16U\r"    # SYN U CR


def test_build_menu_command_defaults_volatile():
    assert build_menu_command("CBRENA1") == b"\x16M\rCBRENA1!"


def test_build_menu_command_persist_uses_nonvolatile():
    assert build_menu_command("CBRENA1", Storage.NONVOLATILE) == b"\x16M\rCBRENA1."


def test_build_query_current_defaults_to_nonvolatile_terminator():
    assert build_query("CBRENA") == b"\x16M\rCBRENA?."


def test_build_query_range_and_default():
    assert build_query("CBRENA", Query.RANGE) == b"\x16M\rCBRENA*."
    assert build_query("CBRENA", Query.DEFAULT) == b"\x16M\rCBRENA^."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_protocol.py -q`
Expected: FAIL — `ImportError: cannot import name 'PREFIX' from 'scanner.protocol'`.

- [ ] **Step 3: Implement constants, enums, and builders**

Replace the contents of `src/scanner/protocol.py` with:
```python
"""Honeywell N36XX serial menu-command protocol: framing and response parsing.

Pure functions only -- no I/O. See the N36XX User's Guide, Chapter 10.
"""

from __future__ import annotations

from enum import Enum

# Menu command prefix and trigger frames (datasheet: SYN=22, M=77, T=84, U=85, CR=13).
PREFIX = b"\x16M\r"      # SYN M CR -- menu command prefix
ACTIVATE = b"\x16T\r"    # SYN T CR -- activate scan
DEACTIVATE = b"\x16U\r"  # SYN U CR -- deactivate scan


class Storage(Enum):
    """Storage table the command terminator selects."""

    VOLATILE = "!"     # lost on power cycle
    NONVOLATILE = "."  # persists through power cycle


class Query(Enum):
    """Query character sent in place of the Data field."""

    CURRENT = "?"  # device's current value
    DEFAULT = "^"  # factory default value
    RANGE = "*"    # range of possible values


def build_menu_command(mnemonic: str, storage: Storage = Storage.VOLATILE) -> bytes:
    """Frame a menu command, e.g. ``build_menu_command("CBRENA1")``."""
    return PREFIX + mnemonic.encode("ascii") + storage.value.encode("ascii")


def build_query(
    tag_subtag: str,
    kind: Query = Query.CURRENT,
    storage: Storage = Storage.NONVOLATILE,
) -> bytes:
    """Frame a query, e.g. ``build_query("CBRENA", Query.RANGE)`` -> ``...CBRENA*.``.

    Queries default to the non-volatile (``.``) terminator to match the
    datasheet's documented examples (e.g. ``cbrena?.``).
    """
    return (
        PREFIX
        + tag_subtag.encode("ascii")
        + kind.value.encode("ascii")
        + storage.value.encode("ascii")
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_protocol.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/protocol.py scanner-cli/tests/test_protocol.py
git commit -m "add protocol constants and command builders"
```

---

## Task 3: protocol.py — response parsing

**Files:**
- Modify: `scanner-cli/src/scanner/protocol.py`
- Test: `scanner-cli/tests/test_protocol.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_protocol.py`:
```python
from scanner.protocol import Response, Status, parse_response


def test_parse_single_ack():
    assert parse_response(b"CBRENA1\x06") == [Response("CBRENA1", Status.ACK)]


def test_parse_single_ack_with_terminator():
    assert parse_response(b"CBRENA1\x06.") == [Response("CBRENA1", Status.ACK)]


def test_parse_nak_and_enq():
    assert parse_response(b"232BAD9\x15.") == [Response("232BAD9", Status.NAK)]
    assert parse_response(b"XYZABC\x05.") == [Response("XYZABC", Status.ENQ)]


def test_parse_multi_response_datasheet_example():
    raw = b"CBRENA1\x06,SSX0\x06,CK20\x06,CCT1\x06,MIN2\x06,MAX60\x06,DFT\x06."
    result = parse_response(raw)
    assert result == [
        Response("CBRENA1", Status.ACK),
        Response("SSX0", Status.ACK),
        Response("CK20", Status.ACK),
        Response("CCT1", Status.ACK),
        Response("MIN2", Status.ACK),
        Response("MAX60", Status.ACK),
        Response("DFT", Status.ACK),
    ]


def test_parse_empty_returns_no_responses():
    assert parse_response(b"") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_protocol.py -q`
Expected: FAIL — `ImportError: cannot import name 'Response' from 'scanner.protocol'`.

- [ ] **Step 3: Implement `Status`, `Response`, and `parse_response`**

Append to `src/scanner/protocol.py`:
```python
from dataclasses import dataclass

# Status bytes the device returns.
ACK = 0x06
ENQ = 0x05
NAK = 0x15

# Punctuation that separates (`,` `;`) or terminates (`.` `!`) commands.
_PUNCTUATION = frozenset(b",;.!")


class Status(Enum):
    """Result reported by the device for a command."""

    ACK = ACK  # good command, processed
    ENQ = ENQ  # invalid Tag or SubTag
    NAK = NAK  # data out of allowable range


_STATUS_BY_BYTE = {member.value: member for member in Status}


@dataclass(frozen=True)
class Response:
    """One echoed command segment plus the device's status for it."""

    payload: str
    status: Status


def parse_response(raw: bytes) -> list[Response]:
    """Parse a device response into ``Response`` segments.

    The device echoes each command's payload with a status byte inserted
    directly before the following punctuation mark. We accumulate payload
    bytes until a status byte, emit a ``Response``, then skip the trailing
    punctuation char if present.
    """
    responses: list[Response] = []
    payload = bytearray()
    i = 0
    while i < len(raw):
        byte = raw[i]
        status = _STATUS_BY_BYTE.get(byte)
        if status is not None:
            responses.append(
                Response(payload.decode("ascii", errors="replace"), status)
            )
            payload.clear()
            if i + 1 < len(raw) and raw[i + 1] in _PUNCTUATION:
                i += 1  # consume the punctuation that follows the status byte
        else:
            payload.append(byte)
        i += 1
    return responses
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_protocol.py -q`
Expected: 10 passed (5 from Task 2 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/protocol.py scanner-cli/tests/test_protocol.py
git commit -m "add response parsing to protocol"
```

---

## Task 4: transport.py — SerialTransport send/read_response

**Files:**
- Modify: `scanner-cli/src/scanner/transport.py`
- Test: `scanner-cli/tests/test_transport.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_transport.py`:
```python
import time

from scanner.transport import SerialTransport


def test_send_then_read_response_roundtrip():
    # pyserial's loop:// echoes written bytes back to the read buffer.
    with SerialTransport("loop://", timeout=1.0) as t:
        t.send(b"CBRENA1\x06.")
        time.sleep(0.05)
        data = t.read_response(quiet=0.1, timeout=1.0)
    assert data == b"CBRENA1\x06."


def test_read_response_returns_empty_when_nothing_sent():
    with SerialTransport("loop://", timeout=1.0) as t:
        data = t.read_response(quiet=0.1, timeout=0.3)
    assert data == b""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_transport.py -q`
Expected: FAIL — `ImportError: cannot import name 'SerialTransport' from 'scanner.transport'`.

- [ ] **Step 3: Implement `SerialTransport` (send/read_response)**

Replace the contents of `src/scanner/transport.py` with:
```python
"""Serial transport -- the only hardware-touching layer."""

from __future__ import annotations

import time

import serial


class SerialTransport:
    """Thin wrapper over a pyserial port with response-aware reads.

    Construct with a port and connection params; the port is not opened until
    ``open()`` (or entering the context manager). Defaults match the N36XX
    factory RS232 setting: 115200 baud, 8 data bits, no parity, 1 stop bit.
    """

    def __init__(
        self,
        port: str,
        baud: int = 115200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        timeout: float = 2.0,
    ) -> None:
        self._serial = serial.serial_for_url(
            port,
            baudrate=baud,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
            do_not_open=True,
        )

    def __enter__(self) -> "SerialTransport":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def open(self) -> None:
        if not self._serial.is_open:
            self._serial.open()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def send(self, data: bytes) -> None:
        self._serial.write(data)
        self._serial.flush()

    def read_response(self, quiet: float = 0.2, timeout: float = 2.0) -> bytes:
        """Read bytes until the line is quiet for ``quiet`` s or ``timeout`` elapses.

        Tolerant of varied ACK/ENQ/NAK response shapes -- we do not assume a
        particular terminator, just a gap in transmission.
        """
        deadline = time.monotonic() + timeout
        buf = bytearray()
        last_rx: float | None = None
        while time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            if waiting:
                buf.extend(self._serial.read(waiting))
                last_rx = time.monotonic()
            elif last_rx is not None and (time.monotonic() - last_rx) >= quiet:
                break
            else:
                time.sleep(0.01)
        return bytes(buf)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_transport.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/transport.py scanner-cli/tests/test_transport.py
git commit -m "add SerialTransport send and read_response"
```

---

## Task 5: transport.py — read_scans + list_ports

**Files:**
- Modify: `scanner-cli/src/scanner/transport.py`
- Test: `scanner-cli/tests/test_transport.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_transport.py`:
```python
from scanner.transport import list_ports


def test_read_scans_yields_complete_lines():
    with SerialTransport("loop://", timeout=1.0) as t:
        t.send(b"12345\r67890\r")
        scans = list(t.read_scans(timeout=0.3))
    assert scans == ["12345", "67890"]


def test_read_scans_handles_crlf():
    with SerialTransport("loop://", timeout=1.0) as t:
        t.send(b"ABC\r\nDEF\r\n")
        scans = list(t.read_scans(timeout=0.3))
    assert scans == ["ABC", "DEF"]


def test_list_ports_returns_a_list():
    assert isinstance(list_ports(), list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_transport.py -q`
Expected: FAIL — `AttributeError: 'SerialTransport' object has no attribute 'read_scans'` (and `ImportError` for `list_ports`).

- [ ] **Step 3: Implement `read_scans`, `_drain_lines`, and `list_ports`**

Add the import near the top of `src/scanner/transport.py` (below `import serial`):
```python
from collections.abc import Iterator

from serial.tools import list_ports as _list_ports
```

Add `read_scans` as a method on `SerialTransport` (after `read_response`):
```python
    def read_scans(self, timeout: float | None = None) -> Iterator[str]:
        """Yield decoded barcode lines as they arrive.

        Splits the incoming stream on CR and/or LF. With ``timeout=None`` this
        runs until interrupted (e.g. KeyboardInterrupt in the caller);
        otherwise it stops after ``timeout`` seconds.
        """
        buf = bytearray()
        deadline = None if timeout is None else time.monotonic() + timeout
        while deadline is None or time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            if waiting:
                buf.extend(self._serial.read(waiting))
                yield from _drain_lines(buf)
            else:
                time.sleep(0.01)
```

Add these module-level functions at the end of the file:
```python
def _drain_lines(buf: bytearray) -> list[str]:
    """Pull complete CR/LF-terminated lines out of ``buf`` (mutates ``buf``)."""
    lines: list[str] = []
    while True:
        cr = buf.find(0x0D)
        lf = buf.find(0x0A)
        candidates = [p for p in (cr, lf) if p != -1]
        if not candidates:
            break
        idx = min(candidates)
        line = bytes(buf[:idx]).decode("ascii", errors="replace").strip()
        del buf[: idx + 1]
        if buf and buf[0] in (0x0D, 0x0A):
            del buf[0]  # consume the paired CRLF/LFCR byte
        if line:
            lines.append(line)
    return lines


def list_ports() -> list:
    """Return available serial ports as pyserial ``ListPortInfo`` objects."""
    return list(_list_ports.comports())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_transport.py -q`
Expected: 5 passed (2 from Task 4 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/transport.py scanner-cli/tests/test_transport.py
git commit -m "add read_scans and list_ports to transport"
```

---

## Task 6: cli.py — group, helpers, `ports`, and `send`

**Files:**
- Modify: `scanner-cli/src/scanner/cli.py`
- Test: `scanner-cli/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli.py`:
```python
from click.testing import CliRunner

from scanner.cli import main


class FakeTransport:
    """Stand-in for SerialTransport: records sent frames, replays a response."""

    last_instance = None

    def __init__(self, *args, **kwargs):
        self.sent = []
        self.response = b""
        self.scans = []
        FakeTransport.last_instance = self

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def send(self, data):
        self.sent.append(data)

    def read_response(self, **kwargs):
        return self.response

    def read_scans(self, timeout=None):
        yield from self.scans


def _patch(monkeypatch, response=b""):
    def factory(*args, **kwargs):
        t = FakeTransport(*args, **kwargs)
        t.response = response
        return t

    monkeypatch.setattr("scanner.cli.SerialTransport", factory)


def test_ports_lists_devices(monkeypatch):
    class Port:
        device = "/dev/cu.usbserial-1"
        description = "FTDI"

    monkeypatch.setattr("scanner.cli.list_ports", lambda: [Port()])
    result = CliRunner().invoke(main, ["ports"])
    assert result.exit_code == 0
    assert "/dev/cu.usbserial-1" in result.output


def test_send_ack_frames_command_and_exits_zero(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(main, ["--port", "loop://", "send", "CBRENA1"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA1!"
    assert "CBRENA1" in result.output


def test_send_persist_uses_nonvolatile(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(
        main, ["--port", "loop://", "send", "CBRENA1", "--persist"]
    )
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA1."


def test_send_nak_exits_one(monkeypatch):
    _patch(monkeypatch, response=b"232BAD9\x15.")
    result = CliRunner().invoke(main, ["--port", "loop://", "send", "232BAD9"])
    assert result.exit_code == 1


def test_send_enq_exits_two(monkeypatch):
    _patch(monkeypatch, response=b"XYZ\x05.")
    result = CliRunner().invoke(main, ["--port", "loop://", "send", "XYZ"])
    assert result.exit_code == 2


def test_send_no_response_exits_three(monkeypatch):
    _patch(monkeypatch, response=b"")
    result = CliRunner().invoke(main, ["--port", "loop://", "send", "CBRENA1"])
    assert result.exit_code == 3


def test_send_without_port_is_usage_error(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(main, ["send", "CBRENA1"])
    assert result.exit_code == 2  # click UsageError
    assert "port" in result.output.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: FAIL — group has no `ports`/`send` commands and no `SerialTransport`/`list_ports` names to patch.

- [ ] **Step 3: Implement the group, helpers, `ports`, and `send`**

Replace the contents of `src/scanner/cli.py` with:
```python
"""Command-line interface for the scanner tool."""

from __future__ import annotations

import sys

import click
import serial

from . import protocol
from .protocol import Status, Storage
from .transport import SerialTransport, list_ports

EXIT_ACK = 0
EXIT_NAK = 1
EXIT_ENQ = 2
EXIT_NO_RESPONSE = 3
EXIT_CONNECTION = 4

_STATUS_EXIT = {Status.ACK: EXIT_ACK, Status.NAK: EXIT_NAK, Status.ENQ: EXIT_ENQ}
_STATUS_MEANING = {
    Status.ACK: "OK (processed)",
    Status.NAK: "NAK: data out of allowable range",
    Status.ENQ: "ENQ: invalid Tag or SubTag",
}


@click.group()
@click.option("--port", "-p", help="Serial port, e.g. /dev/cu.usbserial-XXXX or loop://.")
@click.option("--baud", "-b", default=115200, show_default=True, type=int)
@click.option("--bytesize", default=8, show_default=True, type=int)
@click.option("--parity", default="N", show_default=True)
@click.option("--stopbits", default=1, show_default=True, type=int)
@click.option("--timeout", default=2.0, show_default=True, type=float)
@click.option("--verbose", "-v", is_flag=True, help="Print TX/RX bytes as hex on stderr.")
@click.pass_context
def main(ctx, port, baud, bytesize, parity, stopbits, timeout, verbose):
    """Send Honeywell N36XX barcode commands over serial."""
    ctx.obj = {
        "port": port,
        "baud": baud,
        "bytesize": bytesize,
        "parity": parity,
        "stopbits": stopbits,
        "timeout": timeout,
        "verbose": verbose,
    }


def _connect(ctx) -> SerialTransport:
    cfg = ctx.obj
    if not cfg["port"]:
        raise click.UsageError("--port is required for this command.")
    transport = SerialTransport(
        cfg["port"],
        baud=cfg["baud"],
        bytesize=cfg["bytesize"],
        parity=cfg["parity"],
        stopbits=cfg["stopbits"],
        timeout=cfg["timeout"],
    )
    try:
        transport.open()
    except (serial.SerialException, OSError) as exc:
        click.echo(f"connection error: {exc}", err=True)
        sys.exit(EXIT_CONNECTION)
    return transport


def _exchange(ctx, frame: bytes) -> bytes:
    transport = _connect(ctx)
    try:
        if ctx.obj["verbose"]:
            click.echo(f"TX: {frame.hex(' ')}", err=True)
        transport.send(frame)
        raw = transport.read_response(timeout=ctx.obj["timeout"])
        if ctx.obj["verbose"]:
            click.echo(f"RX: {raw.hex(' ') or '<empty>'}", err=True)
    finally:
        transport.close()
    return raw


def _report_and_exit(raw: bytes) -> None:
    responses = protocol.parse_response(raw)
    if not responses:
        click.echo(
            f"no/garbled response (RX: {raw.hex(' ') or '<empty>'})", err=True
        )
        sys.exit(EXIT_NO_RESPONSE)
    worst = EXIT_ACK
    for r in responses:
        click.echo(f"{r.payload}  [{_STATUS_MEANING[r.status]}]")
        worst = max(worst, _STATUS_EXIT[r.status])
    sys.exit(worst)


@main.command()
def ports():
    """List available serial ports."""
    found = list_ports()
    if not found:
        click.echo("no serial ports found")
        return
    for p in found:
        click.echo(f"{p.device}\t{p.description}")


@main.command()
@click.argument("mnemonic")
@click.option(
    "--persist",
    is_flag=True,
    help="Write to the non-volatile table (.) instead of volatile (!).",
)
@click.pass_context
def send(ctx, mnemonic, persist):
    """Send a menu command, e.g. `scanner -p PORT send CBRENA1`."""
    storage = Storage.NONVOLATILE if persist else Storage.VOLATILE
    frame = protocol.build_menu_command(mnemonic, storage)
    raw = _exchange(ctx, frame)
    _report_and_exit(raw)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/cli.py scanner-cli/tests/test_cli.py
git commit -m "add cli group, ports, and send commands"
```

---

## Task 7: cli.py — `query` command

**Files:**
- Modify: `scanner-cli/src/scanner/cli.py`
- Test: `scanner-cli/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:
```python
def test_query_current_frames_question_mark(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(main, ["--port", "loop://", "query", "CBRENA"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA?."
    assert "CBRENA1" in result.output


def test_query_range_frames_star(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA0-1\x06.")
    result = CliRunner().invoke(
        main, ["--port", "loop://", "query", "CBRENA", "--kind", "range"]
    )
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA*."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: FAIL — `Error: No such command 'query'.`

- [ ] **Step 3: Implement the `query` command**

Add this import to the `from .protocol import ...` line in `src/scanner/cli.py` so it reads:
```python
from .protocol import Query, Status, Storage
```

Add the command (after `send`, before the `if __name__` block):
```python
@main.command()
@click.argument("tag_subtag")
@click.option(
    "--kind",
    type=click.Choice(["current", "default", "range"]),
    default="current",
    show_default=True,
    help="Which value to query.",
)
@click.pass_context
def query(ctx, tag_subtag, kind):
    """Query a setting, e.g. `scanner -p PORT query CBRENA --kind range`."""
    kinds = {
        "current": Query.CURRENT,
        "default": Query.DEFAULT,
        "range": Query.RANGE,
    }
    frame = protocol.build_query(tag_subtag, kinds[kind])
    raw = _exchange(ctx, frame)
    _report_and_exit(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/cli.py scanner-cli/tests/test_cli.py
git commit -m "add cli query command"
```

---

## Task 8: cli.py — `trigger` and `untrigger`

**Files:**
- Modify: `scanner-cli/src/scanner/cli.py`
- Test: `scanner-cli/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:
```python
def test_trigger_sends_activate(monkeypatch):
    _patch(monkeypatch)
    result = CliRunner().invoke(main, ["--port", "loop://", "trigger"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent == [b"\x16T\r"]


def test_untrigger_sends_deactivate(monkeypatch):
    _patch(monkeypatch)
    result = CliRunner().invoke(main, ["--port", "loop://", "untrigger"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent == [b"\x16U\r"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: FAIL — `Error: No such command 'trigger'.`

- [ ] **Step 3: Implement `_send_only`, `trigger`, and `untrigger`**

Add this helper after `_exchange` in `src/scanner/cli.py`:
```python
def _send_only(ctx, frame: bytes) -> None:
    transport = _connect(ctx)
    try:
        if ctx.obj["verbose"]:
            click.echo(f"TX: {frame.hex(' ')}", err=True)
        transport.send(frame)
    finally:
        transport.close()
```

Add the commands (after `query`, before `if __name__`):
```python
@main.command()
@click.pass_context
def trigger(ctx):
    """Activate scanning (SYN T CR). Requires Manual Trigger Mode (TRGMOD)."""
    _send_only(ctx, protocol.ACTIVATE)
    click.echo("trigger activated")


@main.command()
@click.pass_context
def untrigger(ctx):
    """Deactivate scanning (SYN U CR)."""
    _send_only(ctx, protocol.DEACTIVATE)
    click.echo("trigger deactivated")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add scanner-cli/src/scanner/cli.py scanner-cli/tests/test_cli.py
git commit -m "add cli trigger and untrigger commands"
```

---

## Task 9: cli.py — `listen` and `repl`

**Files:**
- Modify: `scanner-cli/src/scanner/cli.py`
- Test: `scanner-cli/tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:
```python
def test_listen_activates_streams_then_deactivates(monkeypatch):
    def factory(*args, **kwargs):
        t = FakeTransport(*args, **kwargs)
        t.scans = ["12345", "67890"]
        return t

    monkeypatch.setattr("scanner.cli.SerialTransport", factory)
    result = CliRunner().invoke(
        main, ["--port", "loop://", "listen", "--seconds", "0.1"]
    )
    assert result.exit_code == 0
    inst = FakeTransport.last_instance
    assert inst.sent[0] == b"\x16T\r"   # activate first
    assert inst.sent[-1] == b"\x16U\r"  # deactivate last
    assert "12345" in result.output
    assert "67890" in result.output


def test_repl_runs_mnemonic_then_quits(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(
        main, ["--port", "loop://", "repl"], input="CBRENA1\n:quit\n"
    )
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA1!"
    assert "CBRENA1" in result.output


def test_repl_trigger_metacommand(monkeypatch):
    _patch(monkeypatch)
    result = CliRunner().invoke(
        main, ["--port", "loop://", "repl"], input=":trigger\n:quit\n"
    )
    assert result.exit_code == 0
    assert b"\x16T\r" in FakeTransport.last_instance.sent
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: FAIL — `Error: No such command 'listen'.`

- [ ] **Step 3: Implement `listen` and `repl`**

Add the commands (after `untrigger`, before `if __name__`):
```python
@main.command()
@click.option(
    "--seconds",
    type=float,
    default=None,
    help="Stop after N seconds (default: until Ctrl-C).",
)
@click.pass_context
def listen(ctx, seconds):
    """Activate the trigger and print decoded barcodes until Ctrl-C."""
    transport = _connect(ctx)
    try:
        transport.send(protocol.ACTIVATE)
        click.echo("listening (Ctrl-C to stop)...", err=True)
        for scan in transport.read_scans(timeout=seconds):
            click.echo(scan)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            transport.send(protocol.DEACTIVATE)
        finally:
            transport.close()


@main.command()
@click.pass_context
def repl(ctx):
    """Interactive prompt: type a mnemonic; :trigger/:untrigger/:listen/:quit."""
    transport = _connect(ctx)
    click.echo("scanner REPL -- type a mnemonic, or :quit to exit", err=True)
    try:
        while True:
            try:
                line = input("scanner> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line in (":quit", ":q"):
                break
            if line == ":trigger":
                transport.send(protocol.ACTIVATE)
                click.echo("trigger activated")
            elif line == ":untrigger":
                transport.send(protocol.DEACTIVATE)
                click.echo("trigger deactivated")
            elif line == ":listen":
                transport.send(protocol.ACTIVATE)
                click.echo("listening (Ctrl-C to stop)...", err=True)
                try:
                    for scan in transport.read_scans():
                        click.echo(scan)
                except KeyboardInterrupt:
                    transport.send(protocol.DEACTIVATE)
                    click.echo("")
            else:
                transport.send(protocol.build_menu_command(line))
                raw = transport.read_response(timeout=ctx.obj["timeout"])
                responses = protocol.parse_response(raw)
                if not responses:
                    click.echo(
                        f"no/garbled response (RX: {raw.hex(' ') or '<empty>'})"
                    )
                for r in responses:
                    click.echo(f"{r.payload}  [{_STATUS_MEANING[r.status]}]")
    finally:
        transport.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd scanner-cli && .venv/bin/pytest tests/test_cli.py -q`
Expected: 14 passed.

- [ ] **Step 5: Run the full suite**

Run: `cd scanner-cli && .venv/bin/pytest -q`
Expected: all tests pass (10 protocol + 5 transport + 14 cli = 29).

- [ ] **Step 6: Commit**

```bash
git add scanner-cli/src/scanner/cli.py scanner-cli/tests/test_cli.py
git commit -m "add cli listen and repl commands"
```

---

## Task 10: README

**Files:**
- Modify: `scanner-cli/README.md`

- [ ] **Step 1: Write the README**

Create `scanner-cli/README.md`:
```markdown
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
```

- [ ] **Step 2: Verify the install instructions work end-to-end**

Run:
```bash
cd scanner-cli && .venv/bin/scanner --help && .venv/bin/scanner ports
```
Expected: help text lists all commands (`ports`, `send`, `query`, `trigger`, `untrigger`, `listen`, `repl`); `ports` prints discovered ports or `no serial ports found`.

- [ ] **Step 3: Commit**

```bash
git add scanner-cli/README.md
git commit -m "add scanner README"
```

---

## Self-Review

**1. Spec coverage:**
- Raw passthrough (`send`) — Task 6. ✔
- Query (`?`/`^`/`*`) — Task 7. ✔
- Trigger / untrigger — Task 8. ✔
- Listen — Task 9. ✔
- REPL — Task 9. ✔
- `ports` enumeration — Task 6. ✔
- Flags-only connection (`--port`/`--baud`/8N1 defaults) — Task 6 group options. ✔
- Volatile-default with `--persist` — Task 6 `send`. ✔
- Protocol framing + parsing (datasheet `cbr?.` example) — Tasks 2–3. ✔
- Transport over pyserial with `loop://` tests — Tasks 4–5. ✔
- Exit codes 0–4 — Task 6 helpers, exercised in Tasks 6–9. ✔
- Manual Trigger Mode caveat — Task 10 README. ✔

**2. Placeholder scan:** No TBD/TODO; every code step contains full code; every test step contains assertions.

**3. Type/name consistency:** `Storage`, `Query`, `Status`, `Response`, `build_menu_command`, `build_query`, `parse_response`, `SerialTransport`, `list_ports`, `read_response`, `read_scans` are defined in Tasks 2–5 and used with identical names in cli (Tasks 6–9) and tests. CLI patches `scanner.cli.SerialTransport` / `scanner.cli.list_ports`, which match the imports added in Task 6. Exit-code constants (`EXIT_ACK..EXIT_CONNECTION`) are defined once in Task 6 and reused.
```
