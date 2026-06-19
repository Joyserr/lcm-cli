"""Tests for lcm_tools.commands.record."""

from __future__ import annotations

import threading

from typer.testing import CliRunner

from lcm_tools.cli import app
from lcm_tools.lcm_log import iter_lcm_log
from lcm_tools.protocol import PacketInfo

runner = CliRunner()


def _make_run_listener(packets):
    """Build a fake run_listener that synchronously feeds *packets*."""

    def fake(callback, mc_addr=None, mc_port=None, **kw):
        for p in packets:
            callback(p)
        return threading.Event()

    return fake


class TestRecord:
    def test_records_to_log_file(self, tmp_path, monkeypatch):
        out = tmp_path / "rec.log"
        pkts = [
            PacketInfo(channel="A", seqno=0, payload=b"\x01\x02", packet_size=10),
            PacketInfo(channel="B", seqno=1, payload=b"\x03", packet_size=5),
            # channel-less fragment must be skipped.
            PacketInfo(channel=None, seqno=2, payload=b"\x04", is_fragment=True),
        ]
        monkeypatch.setattr(
            "lcm_tools.commands.record.run_listener", _make_run_listener(pkts)
        )
        # Neutralize the status-loop sleep so duration=0 exits immediately.
        monkeypatch.setattr("lcm_tools.commands.record.time.sleep", lambda s: None)

        result = runner.invoke(
            app, ["record", "-o", str(out), "--duration", "0"]
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        events = list(iter_lcm_log(out))
        assert [e.channel for e in events] == ["A", "B"]
        assert events[0].data == b"\x01\x02"
        assert events[1].data == b"\x03"
        # Timestamps are microseconds-since-epoch and strictly positive.
        assert all(e.timestamp_us > 0 for e in events)

    def test_channel_filter(self, tmp_path, monkeypatch):
        out = tmp_path / "rec.log"
        pkts = [
            PacketInfo(channel="CAM_LEFT", seqno=0, payload=b"x", packet_size=1),
            PacketInfo(channel="LIDAR", seqno=1, payload=b"y", packet_size=1),
            PacketInfo(channel="CAM_RIGHT", seqno=2, payload=b"z", packet_size=1),
        ]
        monkeypatch.setattr(
            "lcm_tools.commands.record.run_listener", _make_run_listener(pkts)
        )
        monkeypatch.setattr("lcm_tools.commands.record.time.sleep", lambda s: None)

        result = runner.invoke(
            app, ["record", "-o", str(out), "--channel", "CAM.*", "--duration", "0"]
        )
        assert result.exit_code == 0, result.output
        events = list(iter_lcm_log(out))
        assert [e.channel for e in events] == ["CAM_LEFT", "CAM_RIGHT"]

    def test_default_output_filename_pattern(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "lcm_tools.commands.record.run_listener", _make_run_listener([])
        )
        monkeypatch.setattr("lcm_tools.commands.record.time.sleep", lambda s: None)
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["record", "--duration", "0"])
        assert result.exit_code == 0, result.output
        files = list(tmp_path.glob("lcm_*.log"))
        assert len(files) == 1

    def test_invalid_regex_exits_nonzero(self, tmp_path, monkeypatch):
        out = tmp_path / "rec.log"
        monkeypatch.setattr(
            "lcm_tools.commands.record.run_listener", _make_run_listener([])
        )
        result = runner.invoke(
            app, ["record", "-o", str(out), "--channel", "[invalid", "--duration", "0"]
        )
        assert result.exit_code != 0
