"""Command-line interface for the scanner tool."""

from __future__ import annotations

import sys
import time

import click
import serial

from . import protocol
from .protocol import Query, Status, Storage
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


def _send_only(ctx, frame: bytes) -> None:
    transport = _connect(ctx)
    try:
        if ctx.obj["verbose"]:
            click.echo(f"TX: {frame.hex(' ')}", err=True)
        transport.send(frame)
    finally:
        transport.close()


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


def _scan_once(transport, seconds: float) -> str | None:
    """Trigger once and return the first decoded barcode, or None on timeout.

    Does not open or close the transport (the caller owns its lifecycle), so it
    is reusable by both the `scan` command and the REPL `:scan` meta-command.
    """
    deadline = time.monotonic() + seconds
    try:
        transport.send(protocol.ACTIVATE)
        while time.monotonic() < deadline:
            lines = transport.poll_lines()
            if lines:
                return lines[0]
            time.sleep(0.02)
        return None
    finally:
        transport.send(protocol.DEACTIVATE)


@main.command()
@click.option(
    "--seconds",
    type=float,
    default=5.0,
    show_default=True,
    help="Max time to wait for a scan.",
)
@click.pass_context
def scan(ctx, seconds):
    """Trigger one scan over serial and print the first barcode (waits up to N seconds)."""
    transport = _connect(ctx)
    try:
        barcode = _scan_once(transport, seconds)
    finally:
        transport.close()
    if barcode is None:
        click.echo(f"no scan within {seconds:g}s", err=True)
        sys.exit(EXIT_NO_RESPONSE)
    click.echo(barcode)
    sys.stdout.flush()


@main.command()
@click.option(
    "--seconds",
    type=float,
    default=None,
    help="Stop after N seconds (default: until Ctrl-C).",
)
@click.option(
    "--interval",
    type=float,
    default=2.0,
    show_default=True,
    help="Re-assert the serial trigger every N seconds to keep illumination on "
    "(needed in manual/serial trigger mode; set 0 to disable).",
)
@click.pass_context
def listen(ctx, seconds, interval):
    """Activate the trigger and print decoded barcodes until Ctrl-C.

    Re-asserts the trigger on an interval so the engine keeps scanning
    continuously in manual/serial trigger mode (TRGMOD0). Harmless in
    presentation mode.
    """
    transport = _connect(ctx)
    click.echo("listening (Ctrl-C to stop)...", err=True)
    deadline = None if seconds is None else time.monotonic() + seconds
    next_trig: float | None = time.monotonic() if interval and interval > 0 else None
    try:
        while deadline is None or time.monotonic() < deadline:
            if next_trig is not None and time.monotonic() >= next_trig:
                transport.send(protocol.ACTIVATE)
                next_trig += interval
            for scan in transport.poll_lines():
                click.echo(scan)
                sys.stdout.flush()
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            transport.send(protocol.DEACTIVATE)
        finally:
            transport.close()


_REPL_HELP = """\
Commands:
  MNEMONIC    Send a menu command, e.g. CBRENA1; prints ACK/ENQ/NAK.
  :scan       Trigger once; print the first barcode (waits up to 5s).
  :trigger    Activate scanning (SYN T).
  :untrigger  Deactivate scanning (SYN U).
  :listen     Stream decoded barcodes until Ctrl-C.
  :menuhelp   Show known menu-command mnemonics.
  :help       Show this help (alias :?).
  :quit       Exit (alias :q)."""

_MENU_HELP = """\
Known mnemonics (send these; append ? ^ * to query):
  Interface / setup
    PAP232        RS232 serial interface: 115200 8N1, CR+LF suffix, manual trigger
    TERMID0       RS232 interface only (granular; keeps trigger mode)
    232BAD9       Baud 115200 (0=300 ... 8=57600, 9=115200)
    232WRD2       8 data bits, no parity, 1 stop
  Trigger / scan mode
    PAPHHF        Manual trigger (normal)
    PAPPST        Presentation mode (hands-free)
    TRGMOD3       Presentation mode (granular)
    TRGSTO30000   Serial read time-out, ms (0-300000; default 30000)
    DLYGRD0       Good-read delay, ms (0-30000)
    TRGPMS1       Presentation sensitivity (0-20)
  Output formatting
    VSUFCR        Add CR suffix to all symbologies
  Symbology (example)
    CBRENA1       Codabar enable on (0=off)
  Defaults
    DEFALT        Activate defaults
    MNUCDF        Set custom defaults
    MNUCDS        Save custom defaults

Query: append ? (current), ^ (default), * (range), e.g. CBRENA?"""


@main.command()
@click.pass_context
def repl(ctx):
    """Interactive prompt: type a mnemonic, :scan, :listen, :menuhelp, :help, :quit."""
    transport = _connect(ctx)
    click.echo(_REPL_HELP)
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
            if line in (":help", ":?"):
                click.echo(_REPL_HELP)
            elif line == ":menuhelp":
                click.echo(_MENU_HELP)
            elif line == ":scan":
                barcode = _scan_once(transport, 5.0)
                click.echo(barcode if barcode is not None else "no scan within 5s")
            elif line == ":trigger":
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


if __name__ == "__main__":
    main()
