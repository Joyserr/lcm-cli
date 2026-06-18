"""Unit tests for lcm_tools.source module."""

from __future__ import annotations

import time

import pytest

from lcm_tools.lcm_log import LogEvent, write_lcm_log
from lcm_tools.protocol import PacketInfo
from lcm_tools.source import LiveSource, LogFileSource, make_source


class TestLiveSource:
    def test_is_returned_by_make_source_when_no_from(self):
        # make_source returns a LiveSource when `from_path` is None.
        src = make_source(from_path=None, mc_addr="239.255.76.67", mc_port=7667)
        assert isinstance(src, LiveSource)


class TestLogFileSource:
    def test_delivers_all_events_in_order(self, tmp_path):
        # Timestamps 60ms apart: enough to verify spacing via wall-clock,
        # small enough to keep the test fast.
        events = [
            LogEvent(0, 1_000_000, "A", b"\x01"),
            LogEvent(1, 1_000_060, "A", b"\x02"),
            LogEvent(2, 1_000_120, "B", b"\x03"),
        ]
        path = tmp_path / "in.log"
        write_lcm_log(path, events)

        got: list[PacketInfo] = []
        src = LogFileSource(str(path))
        stop = src.start(got.append)
        deadline = time.monotonic() + 2.0
        while len(got) < len(events) and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()

        assert [p.channel for p in got] == ["A", "A", "B"]
        assert [p.payload for p in got] == [b"\x01", b"\x02", b"\x03"]

    def test_spacing_matches_timestamp_delta(self, tmp_path):
        # Two events 100ms apart in log time => ~100ms apart on the wall clock.
        events = [
            LogEvent(0, 0, "A", b"\x01"),
            LogEvent(1, 100_000, "A", b"\x02"),  # 0.1s delta
        ]
        path = tmp_path / "in.log"
        write_lcm_log(path, events)

        got: list[PacketInfo] = []
        src = LogFileSource(str(path))
        stop = src.start(got.append)
        deadline = time.monotonic() + 2.0
        while len(got) < len(events) and time.monotonic() < deadline:
            time.sleep(0.005)
        stop.set()

        assert len(got) == 2

    def test_speed_scales_delta(self, tmp_path):
        # 200ms log delta at 2x speed => ~100ms wall-clock gap.
        events = [
            LogEvent(0, 0, "A", b"\x01"),
            LogEvent(1, 200_000, "A", b"\x02"),  # 0.2s delta
        ]
        path = tmp_path / "in.log"
        write_lcm_log(path, events)

        got: list[PacketInfo] = []
        src = LogFileSource(str(path), speed=2.0)
        stop = src.start(got.append)
        deadline = time.monotonic() + 2.0
        while len(got) < len(events) and time.monotonic() < deadline:
            time.sleep(0.005)
        stop.set()

        assert len(got) == 2

    def test_event_to_packet_shape(self):
        ev = LogEvent(7, 12345, "CH", b"\xaa\xbb")
        pkt = LogFileSource._event_to_packet(ev)
        assert pkt.channel == "CH"
        assert pkt.seqno == 7
        assert pkt.payload == b"\xaa\xbb"
        assert pkt.is_fragment is False


class TestMakeSource:
    def test_returns_logfile_source_when_from_set(self, tmp_path):
        path = tmp_path / "x.log"
        path.write_bytes(b"")
        src = make_source(from_path=str(path))
        assert isinstance(src, LogFileSource)

    def test_returns_live_source_when_from_none(self):
        src = make_source(from_path=None)
        assert isinstance(src, LiveSource)
