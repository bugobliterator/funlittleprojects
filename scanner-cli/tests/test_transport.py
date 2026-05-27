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
