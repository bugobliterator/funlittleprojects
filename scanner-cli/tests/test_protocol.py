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
