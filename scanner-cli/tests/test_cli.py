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
