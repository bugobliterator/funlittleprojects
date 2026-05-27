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
