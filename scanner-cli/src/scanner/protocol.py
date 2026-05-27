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
