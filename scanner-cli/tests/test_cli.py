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

    def poll_lines(self):
        out = self.scans
        self.scans = []
        return out


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


def test_query_current_frames_question_mark(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(main, ["--port", "loop://", "query", "CBRENA"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA?."
    assert "CBRENA1" in result.output


def test_query_range_frames_star(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA0-1\x06.")
    result = CliRunner().invoke(
        main, ["--port", "loop://", "query", "CBRENA", "--kind", "range"]
    )
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA*."


def test_trigger_sends_activate(monkeypatch):
    _patch(monkeypatch)
    result = CliRunner().invoke(main, ["--port", "loop://", "trigger"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent == [b"\x16T\r"]


def test_untrigger_sends_deactivate(monkeypatch):
    _patch(monkeypatch)
    result = CliRunner().invoke(main, ["--port", "loop://", "untrigger"])
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent == [b"\x16U\r"]


def test_listen_activates_streams_then_deactivates(monkeypatch):
    def factory(*args, **kwargs):
        t = FakeTransport(*args, **kwargs)
        t.scans = ["12345", "67890"]
        return t

    monkeypatch.setattr("scanner.cli.SerialTransport", factory)
    result = CliRunner().invoke(
        main, ["--port", "loop://", "listen", "--seconds", "0.1"]
    )
    assert result.exit_code == 0
    inst = FakeTransport.last_instance
    assert inst.sent[0] == b"\x16T\r"   # activate first
    assert inst.sent[-1] == b"\x16U\r"  # deactivate last
    assert "12345" in result.output
    assert "67890" in result.output


def test_repl_runs_mnemonic_then_quits(monkeypatch):
    _patch(monkeypatch, response=b"CBRENA1\x06.")
    result = CliRunner().invoke(
        main, ["--port", "loop://", "repl"], input="CBRENA1\n:quit\n"
    )
    assert result.exit_code == 0
    assert FakeTransport.last_instance.sent[0] == b"\x16M\rCBRENA1!"
    assert "CBRENA1" in result.output


def test_repl_trigger_metacommand(monkeypatch):
    _patch(monkeypatch)
    result = CliRunner().invoke(
        main, ["--port", "loop://", "repl"], input=":trigger\n:quit\n"
    )
    assert result.exit_code == 0
    assert b"\x16T\r" in FakeTransport.last_instance.sent


def test_scan_triggers_and_prints_first_barcode(monkeypatch):
    def factory(*args, **kwargs):
        t = FakeTransport(*args, **kwargs)
        t.scans = ["CU11X25010374"]
        return t

    monkeypatch.setattr("scanner.cli.SerialTransport", factory)
    result = CliRunner().invoke(main, ["--port", "loop://", "scan"])
    assert result.exit_code == 0
    inst = FakeTransport.last_instance
    assert inst.sent[0] == b"\x16T\r"   # triggered the scan
    assert inst.sent[-1] == b"\x16U\r"  # deactivated afterward
    assert result.output.strip() == "CU11X25010374"


def test_scan_times_out_with_no_scan(monkeypatch):
    _patch(monkeypatch)  # no scans
    result = CliRunner().invoke(main, ["--port", "loop://", "scan", "--seconds", "0.2"])
    assert result.exit_code == 3
    assert "no scan" in result.output.lower()


def test_repl_scan_metacommand(monkeypatch):
    def factory(*args, **kwargs):
        t = FakeTransport(*args, **kwargs)
        t.scans = ["CU11X25010374"]
        return t

    monkeypatch.setattr("scanner.cli.SerialTransport", factory)
    result = CliRunner().invoke(
        main, ["--port", "loop://", "repl"], input=":scan\n:quit\n"
    )
    assert result.exit_code == 0
    inst = FakeTransport.last_instance
    assert b"\x16T\r" in inst.sent  # triggered a scan
    assert "CU11X25010374" in result.output
