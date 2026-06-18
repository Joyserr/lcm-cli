"""Unit tests for lcm_tools.lcm_log module."""

from __future__ import annotations

from pathlib import Path

import pytest

from lcm_tools.lcm_log import LogEvent, iter_lcm_log, write_lcm_log


class TestRoundTrip:
    def test_roundtrip_basic(self, tmp_path):
        events = [
            LogEvent(eventnum=0, timestamp_us=1_700_000_000_000_000, channel="A", data=b"\x01\x02"),
            LogEvent(eventnum=1, timestamp_us=1_700_000_001_000_000, channel="B", data=b"hello"),
            LogEvent(
                eventnum=2,
                timestamp_us=1_700_000_002_000_000,
                channel="WITH SPACES & symbols!",
                data=b"\x00" * 200,
            ),
        ]
        path = tmp_path / "out.log"
        write_lcm_log(path, events)

        got = list(iter_lcm_log(path))
        assert len(got) == 3
        for exp, act in zip(events, got):
            assert act.eventnum == exp.eventnum
            assert act.timestamp_us == exp.timestamp_us
            assert act.channel == exp.channel
            assert act.data == exp.data

    def test_roundtrip_empty_data(self, tmp_path):
        events = [LogEvent(0, 1000, "EMPTY", b"")]
        path = tmp_path / "empty.log"
        write_lcm_log(path, events)
        got = list(iter_lcm_log(path))
        assert got[0].data == b""
        assert got[0].channel == "EMPTY"

    def test_roundtrip_unicode_channel(self, tmp_path):
        events = [LogEvent(0, 1000, "中文_チャanel", b"\x09")]
        path = tmp_path / "uni.log"
        write_lcm_log(path, events)
        got = list(iter_lcm_log(path))
        assert got[0].channel == "中文_チャanel"


class TestBadInput:
    def test_bad_sync_word_raises_with_offset(self, tmp_path):
        path = tmp_path / "bad.log"
        # 28 bytes of garbage: magic won't match.
        path.write_bytes(b"\x00" * 28)
        with pytest.raises(ValueError, match="byte offset 0"):
            list(iter_lcm_log(path))

    def test_truncated_header_raises(self, tmp_path):
        path = tmp_path / "trunc.log"
        path.write_bytes(b"\x00" * 10)  # less than 28-byte header
        with pytest.raises(ValueError, match="truncated"):
            list(iter_lcm_log(path))


class TestOfficialSample:
    """Decode the official lcm-logger sample log to verify binary compatibility."""

    def test_decode_official_sample(self):
        sample = Path("lcm_ref/test/python/example.lcmlog")
        if not sample.exists():
            pytest.skip("official example.lcmlog not present")
        events = list(iter_lcm_log(sample))
        assert len(events) >= 1
        # First channel observed in the hex dump is "JOINT_TEST".
        assert events[0].channel == "JOINT_TEST"
        for ev in events:
            assert ev.timestamp_us > 0
            assert isinstance(ev.data, bytes)
