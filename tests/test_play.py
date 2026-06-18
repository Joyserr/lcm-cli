"""Tests for lcm_tools.commands.play."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from lcm_tools.cli import app
from lcm_tools.lcm_log import LogEvent, write_lcm_log

runner = CliRunner()


class TestPlay:
    def test_sends_events_as_multicast_packets(self, tmp_path, monkeypatch):
        # Build a log file with 3 events, tiny timestamps so playback is instant.
        events = [
            LogEvent(0, 1_000_000, "A", b"\x01\x02"),
            LogEvent(1, 1_000_100, "B", b"\x03"),
            LogEvent(2, 1_000_200, "A", b"\x04\x05"),
        ]
        log_path = tmp_path / "demo.log"
        write_lcm_log(log_path, events)

        sent: list[tuple[str, int, bytes]] = []  # (addr, port, data)

        class FakeSock:
            def setsockopt(self, *a, **k):
                pass

            def sendto(self, data, dest):
                sent.append((dest[0], dest[1], bytes(data)))

            def close(self):
                pass

        monkeypatch.setattr(
            "lcm_tools.commands.play.socket.socket", lambda *a, **k: FakeSock()
        )
        # Neutralize any cooperative sleeps.
        monkeypatch.setattr("lcm_tools.commands.play.time.sleep", lambda s: None)

        result = runner.invoke(app, ["play", str(log_path)])
        assert result.exit_code == 0, result.output
        # 3 events sent to the multicast address.
        assert len(sent) == 3
        # Each sent payload is the LCM short-message wire format (magic+seqno+ch\0+data).
        import struct

        from lcm_tools.protocol import LCM2_MAGIC_SHORT

        magic, seqno = struct.unpack("!II", sent[0][2][:8])
        assert magic == LCM2_MAGIC_SHORT
        # Channel "A" appears after the 8-byte header.
        assert sent[0][2][8:].split(b"\x00", 1)[0] == b"A"

    def test_channel_filter(self, tmp_path, monkeypatch):
        events = [
            LogEvent(0, 1_000_000, "CAM_LEFT", b"x"),
            LogEvent(1, 1_000_100, "LIDAR", b"y"),
        ]
        log_path = tmp_path / "demo.log"
        write_lcm_log(log_path, events)

        sent: list[bytes] = []

        class FakeSock:
            def setsockopt(self, *a, **k):
                pass

            def sendto(self, data, dest):
                sent.append(bytes(data))

            def close(self):
                pass

        monkeypatch.setattr(
            "lcm_tools.commands.play.socket.socket", lambda *a, **k: FakeSock()
        )
        monkeypatch.setattr("lcm_tools.commands.play.time.sleep", lambda s: None)

        result = runner.invoke(app, ["play", str(log_path), "--channel", "CAM.*"])
        assert result.exit_code == 0, result.output
        assert len(sent) == 1  # only CAM_LEFT
