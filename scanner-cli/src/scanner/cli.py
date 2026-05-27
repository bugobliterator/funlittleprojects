"""Command-line interface for the scanner tool."""

from __future__ import annotations

import sys

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


if __name__ == "__main__":
    main()
