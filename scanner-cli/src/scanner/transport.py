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
