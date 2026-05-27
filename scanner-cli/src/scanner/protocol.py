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
