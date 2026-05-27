"""Serial transport -- the only hardware-touching layer."""

from __future__ import annotations

import time
from collections.abc import Iterator

import serial
from serial.tools import list_ports as _list_ports


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
        self._scan_buf = bytearray()  # persistent assembly buffer for poll_lines

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

    def poll_lines(self) -> list[str]:
        """Non-blocking: drain any waiting bytes and return complete CR/LF lines.

        Buffers partial lines across calls, so a caller can interleave this with
        other work (e.g. re-asserting a serial trigger on an interval).
        """
        waiting = self._serial.in_waiting
        if waiting:
            self._scan_buf.extend(self._serial.read(waiting))
        return _drain_lines(self._scan_buf)

    def read_scans(self, timeout: float | None = None) -> Iterator[str]:
        """Yield decoded barcode lines as they arrive.

        Splits the incoming stream on CR and/or LF. With ``timeout=None`` this
        runs until interrupted (e.g. KeyboardInterrupt in the caller);
        otherwise it stops after ``timeout`` seconds.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while deadline is None or time.monotonic() < deadline:
            lines = self.poll_lines()
            if lines:
                yield from lines
            else:
                time.sleep(0.01)


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
