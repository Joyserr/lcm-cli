# A 组:录制与回放 + 离线源 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `lcm record` / `lcm play` 命令,并给 `topic echo`/`stats`/`list` 加 `--from <file.log>` 离线源,构成纯 Python、零依赖、二进制兼容 `lcm-logger` 的录制→回放→反复分析闭环。

**Architecture:** 新增 `lcm_log.py`(标准 LCM 日志二进制 I/O)和 `source.py`(`PacketSource` 抽象:实时组播 `LiveSource` 与离线日志 `LogFileSource` 走同一管线)。`record`/`play` 为顶层命令,现有命令通过最小改造接入 `--from`。

**Tech Stack:** Python ≥3.9, `typer`, `rich`, 纯 `struct`/`socket`, `pytest` + `pytest-timeout`。

**Spec:** `docs/superpowers/specs/2026-06-18-record-replay-design.md`

---

## 文件结构

| 路径 | 职责 | 动作 |
|------|------|------|
| `src/lcm_tools/lcm_log.py` | LCM 日志二进制读写(`LogEvent`, `write_lcm_log`, `iter_lcm_log`) | 新建 |
| `src/lcm_tools/source.py` | 统一数据源抽象(`PacketSource`, `LiveSource`, `LogFileSource`, `make_source`) | 新建 |
| `src/lcm_tools/commands/record.py` | `lcm record` 命令 | 新建 |
| `src/lcm_tools/commands/play.py` | `lcm play` 命令(含组播 sender) | 新建 |
| `src/lcm_tools/cli.py` | 注册 `record`/`play` 顶层命令 | 修改 |
| `src/lcm_tools/commands/topic_echo.py` | 加 `--from` 选项 | 修改 |
| `src/lcm_tools/commands/topic_stats.py` | 加 `--from` 选项 | 修改 |
| `src/lcm_tools/commands/topic_list.py` | 加 `--from` 选项 | 修改 |
| `tests/test_lcm_log.py` | 日志读写测试 | 新建 |
| `tests/test_source.py` | 数据源抽象测试 | 新建 |
| `tests/test_record.py` | record 命令测试 | 新建 |
| `tests/test_play.py` | play 命令测试 | 新建 |
| `tests/data/.gitkeep` | 测试 fixture 目录 | 新建 |
| `README.md` / `README_zh.md` | 文档更新 | 修改 |

---

## Task 1: LCM 日志二进制读写模块

**Files:**
- Create: `src/lcm_tools/lcm_log.py`
- Test: `tests/test_lcm_log.py`

### Step 1.1: [ ] 写 round-trip 测试(先失败)

Create `tests/test_lcm_log.py`:

```python
"""Unit tests for lcm_tools.lcm_log module."""

from __future__ import annotations

import struct

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
```

### Step 1.2: [ ] 运行测试确认失败

Run: `pytest tests/test_lcm_log.py -v`
Expected: FAIL — `ModuleNotFoundError: lcm_tools.lcm_log`

### Step 1.3: [ ] 实现 lcm_log.py

Create `src/lcm_tools/lcm_log.py`:

```python
"""Pure-Python reader/writer for the standard LCM event log format.

Binary-compatible with ``lcm-logger`` / ``lcm-logplayer`` / ``lcm.EventLog``.
Format spec: https://lcm-proj.github.io/lcm/content/log-file-format.html

Each event record (big-endian):
    magic(uint32=0xEDA1DA01) eventnum(int64) timestamp(int64, microseconds since epoch)
    chan_len(int32) data_len(int32) channel(chan_len bytes, NO null terminator) data(data_len bytes)

Header = 4 + 8 + 8 + 4 + 4 = 28 bytes; struct format "!Iqqii".
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Union

# Sync word at the start of every event record.
LCM_LOG_MAGIC: int = 0xEDA1DA01
_HEADER_FMT: str = "!Iqqii"  # magic, eventnum, timestamp, chan_len, data_len
_HEADER_SIZE: int = struct.calcsize(_HEADER_FMT)  # 28


@dataclass(frozen=True)
class LogEvent:
    """A single event in an LCM log file."""

    eventnum: int
    timestamp_us: int  # microseconds since the Unix epoch
    channel: str
    data: bytes


def write_lcm_log(path: Union[str, Path], events: Iterator[LogEvent]) -> None:
    """Write *events* to *path* in the standard LCM log format.

    Overwrites any existing file. *events* may be a list or any iterable;
    it is consumed in order. Event numbers in the file are taken from the
    LogEvent fields as given.
    """
    with open(path, "wb") as f:
        for ev in events:
            channel_bytes = ev.channel.encode("utf-8")
            f.write(
                struct.pack(
                    _HEADER_FMT,
                    LCM_LOG_MAGIC,
                    int(ev.eventnum),
                    int(ev.timestamp_us),
                    len(channel_bytes),
                    len(ev.data),
                )
            )
            f.write(channel_bytes)
            f.write(ev.data)


def iter_lcm_log(path: Union[str, Path]) -> Iterator[LogEvent]:
    """Yield ``LogEvent`` records from an LCM log file, in file order.

    Raises ``ValueError`` (with byte offset) if the sync word at an event
    boundary does not match, rather than silently skipping.
    """
    offset = 0
    with open(path, "rb") as f:
        while True:
            header = f.read(_HEADER_SIZE)
            if not header:
                return  # clean EOF
            if len(header) < _HEADER_SIZE:
                raise ValueError(
                    f"truncated event header at byte offset {offset}: "
                    f"expected {_HEADER_SIZE} bytes, got {len(header)}"
                )
            magic, eventnum, timestamp, chan_len, data_len = struct.unpack(
                _HEADER_FMT, header
            )
            if magic != LCM_LOG_MAGIC:
                raise ValueError(
                    f"bad sync word at byte offset {offset}: "
                    f"expected 0x{LCM_LOG_MAGIC:08x}, got 0x{magic:08x}"
                )
            channel_bytes = f.read(chan_len)
            data = f.read(data_len)
            if len(channel_bytes) < chan_len or len(data) < data_len:
                raise ValueError(
                    f"truncated event body at byte offset {offset}: "
                    f"channel/payload shorter than declared length"
                )
            try:
                channel = channel_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"undecodable channel name at byte offset {offset}: {exc}"
                ) from exc
            yield LogEvent(
                eventnum=eventnum,
                timestamp_us=timestamp,
                channel=channel,
                data=data,
            )
            offset += _HEADER_SIZE + chan_len + data_len
```

### Step 1.4: [ ] 运行测试确认通过

Run: `pytest tests/test_lcm_log.py -v`
Expected: PASS (3 tests)

### Step 1.5: [ ] 写官方样本兼容测试(先失败)

Append to `tests/test_lcm_log.py`:

```python
class TestOfficialSample:
    """Decode the official lcm-logger sample log to verify binary compatibility."""

    def test_decode_official_sample(self):
        sample = Path("lcm_ref/test/python/example.lcmlog")
        if not sample.exists():
            pytest.skip("official example.lcmlog not present")
        events = list(iter_lcm_log(sample))
        # Must decode at least one event without raising.
        assert len(events) >= 1
        # First channel observed in the hex dump is "JOINT_TEST".
        assert events[0].channel == "JOINT_TEST"
        # Every event must carry data and a sane timestamp.
        for ev in events:
            assert ev.timestamp_us > 0
            assert isinstance(ev.data, bytes)
```

Add the import `from pathlib import Path` at the top of the test file (next to existing imports).

### Step 1.6: [ ] 运行兼容测试确认通过

Run: `pytest tests/test_lcm_log.py::TestOfficialSample -v`
Expected: PASS — confirms `iter_lcm_log` decodes the official sample (first channel `JOINT_TEST`).

### Step 1.7: [ ] 提交

```bash
git add src/lcm_tools/lcm_log.py tests/test_lcm_log.py
git commit -m "feat(lcm_log): 纯Python LCM日志读写,二进制兼容lcm-logger"
```

---

## Task 2: 统一数据源抽象层

**Files:**
- Create: `src/lcm_tools/source.py`
- Test: `tests/test_source.py`

### Step 2.1: [ ] 写 LiveSource 测试(先失败)

Create `tests/test_source.py`:

```python
"""Unit tests for lcm_tools.source module."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from lcm_tools.protocol import PacketInfo
from lcm_tools.source import LiveSource, LogFileSource, make_source


class TestLiveSource:
    def test_is_callable_with_make_source_when_no_from(self):
        # make_source returns a LiveSource when `from_path` is None.
        src = make_source(from_path=None, mc_addr="239.255.76.67", mc_port=7667)
        assert isinstance(src, LiveSource)
```

> Note: we do NOT actually start a real multicast socket in unit tests — `LiveSource.start` just delegates to `run_listener`, which we trust is already tested. We only assert the factory wiring here.

### Step 2.2: [ ] 运行测试确认失败

Run: `pytest tests/test_source.py -v`
Expected: FAIL — `ModuleNotFoundError: lcm_tools.source`

### Step 2.3: [ ] 实现 source.py

Create `src/lcm_tools/source.py`:

```python
"""Unified packet data-source abstraction.

Both the live multicast network and an offline LCM ``.log`` file expose the
same interface (``PacketSource``), so every consumer command can be agnostic
about where its packets come from. This is the structural backbone that the
``--from <file.log>`` option and the ``record``/``play`` commands build on.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from typing import Callable, Optional, Protocol

from lcm_tools.lcm_log import LogEvent, iter_lcm_log
from lcm_tools.listener import (
    DEFAULT_MC_ADDR,
    DEFAULT_MC_PORT,
    run_listener,
)
from lcm_tools.protocol import PacketInfo

PacketCallback = Callable[[PacketInfo], None]


class PacketSource(Protocol):
    """Anything that delivers parsed LCM packets to a callback."""

    def start(self, callback: PacketCallback) -> threading.Event:
        """Begin delivery on a background thread.

        Returns a ``threading.Event`` the caller sets to stop delivery.
        """
        ...


class LiveSource:
    """Packets from the live UDP multicast group (wraps run_listener)."""

    def __init__(
        self,
        mc_addr: str = DEFAULT_MC_ADDR,
        mc_port: int = DEFAULT_MC_PORT,
        interface: Optional[str] = None,
    ) -> None:
        self.mc_addr = mc_addr
        self.mc_port = mc_port
        self.interface = interface

    def start(self, callback: PacketCallback) -> threading.Event:
        return run_listener(
            callback,
            mc_addr=self.mc_addr,
            mc_port=self.mc_port,
            interface=self.interface,
        )


class LogFileSource:
    """Packets replayed from an LCM ``.log`` file at the original cadence.

    Reads events in file order and delivers each as a ``PacketInfo`` (short
    message shape: channel + data as payload). Adjacent events are spaced by
    their timestamp delta (scaled by ``speed``), so consumers see realistic
    timing. Optionally stops after ``duration`` seconds of wall-clock time.
    """

    def __init__(
        self,
        path: str,
        speed: float = 1.0,
        duration: Optional[float] = None,
    ) -> None:
        self.path = path
        self.speed = speed
        self.duration = duration

    def start(self, callback: PacketCallback) -> threading.Event:
        stop_event = threading.Event()

        def _worker() -> None:
            try:
                events = iter_lcm_log(self.path)
                first = True
                prev_ts_us: Optional[int] = None
                start_wall = time.monotonic()
                for ev in events:
                    if stop_event.is_set():
                        return
                    if self.duration is not None and (
                        time.monotonic() - start_wall
                    ) >= self.duration:
                        return
                    if not first and prev_ts_us is not None and self.speed > 0:
                        delta = (ev.timestamp_us - prev_ts_us) / 1_000_000.0 / self.speed
                        if delta > 0:
                            # Sleep cooperatively: check stop_event while waiting.
                            self._sleep_interruptible(delta, stop_event)
                            if stop_event.is_set():
                                return
                    prev_ts_us = ev.timestamp_us
                    first = False
                    callback(self._event_to_packet(ev))
            except Exception:
                # Surface errors on the calling thread via stderr-style
                # behavior is intentionally avoided; the listener thread is a
                # daemon. Commands wrap their own error handling.
                if not stop_event.is_set():
                    raise

        t = threading.Thread(target=_worker, daemon=True, name="lcm-logsource")
        t.start()
        return stop_event

    @staticmethod
    def _sleep_interruptible(seconds: float, stop_event: threading.Event) -> None:
        """Sleep for *seconds*, but wake promptly when stop_event is set."""
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            if stop_event.wait(min(remaining, 0.05)):
                return

    @staticmethod
    def _event_to_packet(ev: LogEvent) -> PacketInfo:
        """Map a log event to a PacketInfo (short-message shape)."""
        return PacketInfo(
            channel=ev.channel,
            seqno=ev.eventnum,
            payload=ev.data,
            packet_size=len(ev.data),
            sender_addr=("", 0),
            is_fragment=False,
        )


def make_source(
    from_path: Optional[str] = None,
    mc_addr: str = DEFAULT_MC_ADDR,
    mc_port: int = DEFAULT_MC_PORT,
    interface: Optional[str] = None,
    speed: float = 1.0,
    duration: Optional[float] = None,
) -> PacketSource:
    """Factory: pick LogFileSource when ``from_path`` is set, else LiveSource."""
    if from_path is not None:
        return LogFileSource(from_path, speed=speed, duration=duration)
    return LiveSource(mc_addr=mc_addr, mc_port=mc_port, interface=interface)
```

### Step 2.4: [ ] 运行测试确认通过

Run: `pytest tests/test_source.py -v`
Expected: PASS (1 test)

### Step 2.5: [ ] 写 LogFileSource 节奏投递测试(先失败)

Append to `tests/test_source.py`:

```python
class TestLogFileSource:
    def test_delivers_all_events_in_order(self, tmp_path, monkeypatch):
        # Build a small log file.
        from lcm_tools.lcm_log import LogEvent, write_lcm_log

        events = [
            LogEvent(0, 1_000_000, "A", b"\x01"),
            LogEvent(1, 1_100_000, "A", b"\x02"),
            LogEvent(2, 1_200_000, "B", b"\x03"),
        ]
        path = tmp_path / "in.log"
        write_lcm_log(path, events)

        # Neutralize real sleeps so the test is fast.
        sleeps: list[float] = []
        monkeypatch.setattr(
            "lcm_tools.source.time.sleep",
            lambda s: sleeps.append(s),
        )

        got: list[PacketInfo] = []
        src = LogFileSource(str(path))
        stop = src.start(got.append)
        # Spin until the worker thread finishes delivering all events.
        deadline = time.monotonic() + 2.0
        while len(got) < len(events) and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()

        assert [p.channel for p in got] == ["A", "A", "B"]
        assert [p.payload for p in got] == [b"\x01", b"\x02", b"\x03"]
        # Timestamp deltas: 0.1s, 0.1s (first event has no preceding sleep).
        assert len(sleeps) == 2
        assert all(abs(s - 0.1) < 0.01 for s in sleeps)
```

> **Implementation note:** `LogFileSource` uses `_sleep_interruptible`, which internally calls `stop_event.wait(...)` — it does **not** call `time.sleep` directly. To make this test deterministic and assert the computed deltas, we will refactor `_sleep_interruptible` to record the *intended* total sleep. Update the implementation below before running this test. (See Step 2.6.)

### Step 2.6: [ ] 调整 _sleep_interruptible 以便测试可观测

Replace the `_sleep_interruptible` method in `src/lcm_tools/source.py` with a version that honors a monkeypatchable `time.sleep` for the cooperative wait, so tests can assert deltas:

```python
    @staticmethod
    def _sleep_interruptible(seconds: float, stop_event: threading.Event) -> None:
        """Sleep for *seconds*, waking promptly when stop_event is set.

        Uses time.sleep (monkeypatchable in tests) for the actual wait, but
        re-checks stop_event frequently so a stop request interrupts the sleep.
        """
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            if stop_event.is_set():
                return
            time.sleep(min(remaining, 0.05))
```

This uses `time.sleep` (the test monkeypatches `lcm_tools.source.time.sleep`) while still remaining interruptible via the stop_event check loop.

### Step 2.7: [ ] 运行 LogFileSource 测试确认通过

Run: `pytest tests/test_source.py::TestLogFileSource -v`
Expected: PASS

### Step 2.8: [ ] 写 make_source 工厂测试

Append to `tests/test_source.py`:

```python
class TestMakeSource:
    def test_returns_logfile_source_when_from_set(self, tmp_path):
        path = tmp_path / "x.log"
        path.write_bytes(b"")
        src = make_source(from_path=str(path))
        assert isinstance(src, LogFileSource)

    def test_returns_live_source_when_from_none(self):
        src = make_source(from_path=None)
        assert isinstance(src, LiveSource)
```

Run: `pytest tests/test_source.py -v`
Expected: PASS (all)

### Step 2.9: [ ] 提交

```bash
git add src/lcm_tools/source.py tests/test_source.py
git commit -m "feat(source): 统一数据源抽象(实时组播/离线日志同一管线)"
```

---

## Task 3: `lcm record` 命令

**Files:**
- Create: `src/lcm_tools/commands/record.py`
- Modify: `src/lcm_tools/cli.py`
- Test: `tests/test_record.py`

### Step 3.1: [ ] 写 record 测试(先失败)

Create `tests/test_record.py`:

```python
"""Tests for lcm_tools.commands.record."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from lcm_tools.cli import app


runner = CliRunner()


def _fake_packet_iter(packets):
    """Return a callback that feeds *packets* into a collector, then a stop hook."""
    collected = []

    def cb(pkt):
        collected.append(pkt)

    return cb, collected


class TestRecord:
    def test_records_to_log_file(self, tmp_path, monkeypatch):
        from lcm_tools.protocol import PacketInfo
        from lcm_tools.lcm_log import iter_lcm_log

        out = tmp_path / "rec.log"
        pkts = [
            PacketInfo(channel="A", seqno=0, payload=b"\x01\x02", packet_size=10),
            PacketInfo(channel="B", seqno=1, payload=b"\x03", packet_size=5),
            PacketInfo(channel=None, seqno=2, payload=b"\x04", is_fragment=True),  # skipped
        ]

        def fake_run_listener(callback, mc_addr=None, mc_port=None, **kw):
            for p in pkts:
                callback(p)
            import threading

            ev = threading.Event()
            return ev

        # record uses LiveSource.start -> run_listener; patch at the listener module.
        monkeypatch.setattr(
            "lcm_tools.listener.run_listener", fake_run_listener
        )

        result = runner.invoke(
            app, ["record", "-o", str(out), "--duration", "0"]
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        events = list(iter_lcm_log(out))
        # Only packets with a channel are recorded.
        assert [e.channel for e in events] == ["A", "B"]
        assert events[0].data == b"\x01\x02"

    def test_channel_filter(self, tmp_path, monkeypatch):
        from lcm_tools.protocol import PacketInfo
        from lcm_tools.lcm_log import iter_lcm_log

        out = tmp_path / "rec.log"
        pkts = [
            PacketInfo(channel="CAM_LEFT", seqno=0, payload=b"x", packet_size=1),
            PacketInfo(channel="LIDAR", seqno=1, payload=b"y", packet_size=1),
            PacketInfo(channel="CAM_RIGHT", seqno=2, payload=b"z", packet_size=1),
        ]

        def fake_run_listener(callback, mc_addr=None, mc_port=None, **kw):
            for p in pkts:
                callback(p)
            import threading

            return threading.Event()

        monkeypatch.setattr("lcm_tools.listener.run_listener", fake_run_listener)

        result = runner.invoke(
            app, ["record", "-o", str(out), "--channel", "CAM.*", "--duration", "0"]
        )
        assert result.exit_code == 0, result.output
        events = list(iter_lcm_log(out))
        assert [e.channel for e in events] == ["CAM_LEFT", "CAM_RIGHT"]
```

### Step 3.2: [ ] 运行测试确认失败

Run: `pytest tests/test_record.py -v`
Expected: FAIL — no `record` command registered.

### Step 3.3: [ ] 实现 record.py

Create `src/lcm_tools/commands/record.py`:

```python
"""``lcm record`` — record live LCM multicast traffic to a standard ``.log`` file.

Output is binary-compatible with lcm-logger / lcm-logplayer / lcm.EventLog.
By default all channels are recorded; ``--channel`` applies a regex filter.
Only packets carrying a channel name are written (short messages and the
first fragment of a fragmented message), per the design decision to keep the
log free of channel-less fragment noise.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from lcm_tools.lcm_log import LogEvent, write_lcm_log
from lcm_tools.listener import run_listener
from lcm_tools.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT, PacketInfo

_console = Console()


def _default_filename() -> str:
    return f"lcm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


def record(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .log file. Default: lcm_<YYYYMMDD_HHMMSS>.log",
    ),
    channel: Optional[str] = typer.Option(
        None,
        "--channel",
        help="Regex to filter channels (e.g. 'CAM.*'). Default: record all.",
    ),
    duration: Optional[float] = typer.Option(
        None,
        "--duration",
        "-d",
        help="Stop recording after this many seconds. Default: until Ctrl+C.",
    ),
    lcm_url: str = typer.Option(
        DEFAULT_MC_ADDR, "--lcm-url", help="LCM multicast address."
    ),
    lcm_port: int = typer.Option(
        DEFAULT_MC_PORT, "--lcm-port", help="LCM multicast port."
    ),
) -> None:
    """Record live LCM traffic to a .log file (like ``lcm-logger``)."""
    out_path = Path(output) if output else Path(_default_filename())

    pattern = None
    if channel:
        try:
            pattern = re.compile(channel)
        except re.error as exc:
            _console.print(f"[red]Invalid regex pattern:[/red] {exc}")
            raise typer.Exit(code=1)

    # Buffer of events accumulated on the listener thread; flushed at the end.
    events: List[LogEvent] = []
    lock = threading.Lock()
    eventnum = [0]

    def _on_packet(pkt: PacketInfo) -> None:
        if not pkt.has_channel:
            return
        assert pkt.channel is not None
        if pattern is not None and not pattern.search(pkt.channel):
            return
        ev = LogEvent(
            eventnum=eventnum[0],
            timestamp_us=int(time.time() * 1_000_000),
            channel=pkt.channel,
            data=pkt.payload,
        )
        with lock:
            eventnum[0] += 1
            events.append(ev)

    _console.print(
        f"[bold]Recording →[/bold] [cyan]{out_path}[/cyan]  "
        f"(multicast: {lcm_url}:{lcm_port}, "
        f"{'channel: ' + channel if channel else 'all channels'}, "
        f"Ctrl+C to stop)"
    )

    stop_event = run_listener(_on_packet, mc_addr=lcm_url, mc_port=lcm_port)
    start = time.monotonic()

    try:
        # Status loop: refresh a one-line progress display every 0.5s.
        while True:
            time.sleep(0.5)
            with lock:
                n = len(events)
            elapsed = time.monotonic() - start
            size = out_path.stat().st_size if out_path.exists() else 0
            _console.print(
                f"\r[dim]events: {n}  |  size: {size / 1024:.1f} KB  "
                f"|  elapsed: {elapsed:.0f}s[/dim]",
                end="",
            )
            if duration is not None and elapsed >= duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        # Clear the progress line, then flush buffered events to disk.
        _console.print()
        with lock:
            write_lcm_log(out_path, list(events))

    with lock:
        total = len(events)
    _console.print(
        f"[green]Recorded {total} events →[/green] [cyan]{out_path}[/cyan]"
    )
```

### Step 3.4: [ ] 注册 record 命令到 cli.py

Modify `src/lcm_tools/cli.py`: add import after the other command imports (line 19):

```python
from lcm_tools.commands.record import record
from lcm_tools.commands.topic_stats import stats
```

Then register it (after the `topic` typer group is added, before the `node` typer):

```python
app.command(name="record", help="Record live LCM traffic to a .log file.")(record)
```

(Place this after the `topic` group setup and before `app.add_typer(node_app, ...)`.)

### Step 3.5: [ ] 运行 record 测试确认通过

Run: `pytest tests/test_record.py -v`
Expected: PASS (2 tests)

### Step 3.6: [ ] 提交

```bash
git add src/lcm_tools/commands/record.py src/lcm_tools/cli.py tests/test_record.py
git commit -m "feat(record): lcm record 命令录制组播流量到标准.log"
```

---

## Task 4: `lcm play` 命令

**Files:**
- Create: `src/lcm_tools/commands/play.py`
- Modify: `src/lcm_tools/cli.py`
- Test: `tests/test_play.py`

### Step 4.1: [ ] 写 play 测试(先失败)

Create `tests/test_play.py`:

```python
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
            def sendto(self, data, dest):
                sent.append((dest[0], dest[1], bytes(data)))

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
            def sendto(self, data, dest):
                sent.append(bytes(data))

        monkeypatch.setattr(
            "lcm_tools.commands.play.socket.socket", lambda *a, **k: FakeSock()
        )
        monkeypatch.setattr("lcm_tools.commands.play.time.sleep", lambda s: None)

        result = runner.invoke(app, ["play", str(log_path), "--channel", "CAM.*"])
        assert result.exit_code == 0, result.output
        assert len(sent) == 1  # only CAM_LEFT
```

### Step 4.2: [ ] 运行测试确认失败

Run: `pytest tests/test_play.py -v`
Expected: FAIL — no `play` command.

### Step 4.3: [ ] 实现 play.py

Create `src/lcm_tools/commands/play.py`:

```python
"""``lcm play`` — replay a standard LCM ``.log`` file to the multicast network.

Reads events in file order and re-publishes each on the multicast group as a
fresh LCM short-message datagram, spacing them by their original timestamp
delta (scaled by ``--speed``). This is the counterpart to ``lcm record`` and
is wire-compatible with logs produced by ``lcm-logger``.
"""

from __future__ import annotations

import re
import socket
import struct
import time
from typing import Optional

import typer
from rich.console import Console

from lcm_tools.lcm_log import iter_lcm_log
from lcm_tools.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT, LCM2_MAGIC_SHORT

_console = Console()


def _build_wire_packet(channel: str, data: bytes, seqno: int) -> bytes:
    """Build a short-message LCM wire packet (magic + seqno + channel\\0 + data)."""
    header = struct.pack("!II", LCM2_MAGIC_SHORT, seqno)
    return header + channel.encode("utf-8") + b"\x00" + data


def play(
    file: str = typer.Argument(..., help="Path to the .log file to replay."),
    speed: float = typer.Option(
        1.0, "--speed", "-s", help="Playback speed multiplier (0.5=half, 2.0=double)."
    ),
    loop: bool = typer.Option(False, "--loop", help="Loop playback forever."),
    channel: Optional[str] = typer.Option(
        None, "--channel", help="Regex to filter channels (e.g. 'CAM.*')."
    ),
    lcm_url: str = typer.Option(
        DEFAULT_MC_ADDR, "--lcm-url", help="LCM multicast address to publish to."
    ),
    lcm_port: int = typer.Option(
        DEFAULT_MC_PORT, "--lcm-port", help="LCM multicast port to publish to."
    ),
) -> None:
    """Replay an LCM .log file to the multicast network (like ``lcm-logplayer``)."""
    pattern = None
    if channel:
        try:
            pattern = re.compile(channel)
        except re.error as exc:
            _console.print(f"[red]Invalid regex pattern:[/red] {exc}")
            raise typer.Exit(code=1)

    _console.print(
        f"[bold]Playing[/bold] [cyan]{file}[/cyan] → "
        f"multicast {lcm_url}:{lcm_port}  (speed {speed}x"
        f"{', loop' if loop else ''})"
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # Default TTL for multicast; allow it to reach the local segment.
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    except OSError:
        pass
    dest = (lcm_url, lcm_port)

    try:
        while True:
            played = 0
            prev_ts_us: Optional[int] = None
            for ev in iter_lcm_log(file):
                if pattern is not None and not pattern.search(ev.channel):
                    continue
                if prev_ts_us is not None and speed > 0:
                    delta = (ev.timestamp_us - prev_ts_us) / 1_000_000.0 / speed
                    if delta > 0:
                        time.sleep(delta)
                prev_ts_us = ev.timestamp_us
                sock.sendto(_build_wire_packet(ev.channel, ev.data, ev.eventnum), dest)
                played += 1
            _console.print(f"[dim]Played {played} events.[/dim]")
            if not loop:
                break
    except KeyboardInterrupt:
        _console.print("\n[dim]Stopped.[/dim]")
    finally:
        sock.close()
```

### Step 4.4: [ ] 注册 play 命令到 cli.py

Modify `src/lcm_tools/cli.py`: add import alongside the record import:

```python
from lcm_tools.commands.play import play
from lcm_tools.commands.record import record
```

And register (next to the record registration):

```python
app.command(name="record", help="Record live LCM traffic to a .log file.")(record)
app.command(name="play", help="Replay an LCM .log file to the multicast network.")(play)
```

### Step 4.5: [ ] 运行 play 测试确认通过

Run: `pytest tests/test_play.py -v`
Expected: PASS (2 tests)

### Step 4.6: [ ] 提交

```bash
git add src/lcm_tools/commands/play.py src/lcm_tools/cli.py tests/test_play.py
git commit -m "feat(play): lcm play 命令按原始节奏回放.log到组播"
```

---

## Task 5: echo / stats / list 接入 `--from`

**Files:**
- Modify: `src/lcm_tools/commands/topic_echo.py`
- Modify: `src/lcm_tools/commands/topic_stats.py`
- Modify: `src/lcm_tools/commands/topic_list.py`
- Test: extend `tests/test_record.py` with integration coverage

### Step 5.1: [ ] 写 echo --from 集成测试(先失败)

Append to `tests/test_record.py` (renamed conceptually to an integration file; keeping it in test_record.py to minimize new files):

```python
class TestEchoFromLog:
    def test_echo_reads_from_log_file(self, tmp_path):
        from lcm_tools.lcm_log import LogEvent, write_lcm_log
        from typer.testing import CliRunner

        from lcm_tools.cli import app

        events = [
            LogEvent(0, 1_000_000, "EXAMPLE", b"\xaa\xbb"),
            LogEvent(1, 1_000_100, "EXAMPLE", b"\xcc\xdd"),
        ]
        log_path = tmp_path / "demo.log"
        write_lcm_log(log_path, events)

        runner = CliRunner()
        result = runner.invoke(app, ["topic", "echo", "EXAMPLE", "--from", str(log_path)])
        assert result.exit_code == 0, result.output
        # Default panel display mentions the channel and a hex preview.
        assert "EXAMPLE" in result.output
```

### Step 5.2: [ ] 运行测试确认失败

Run: `pytest tests/test_record.py::TestEchoFromLog -v`
Expected: FAIL — `--from` option doesn't exist on echo.

### Step 5.3: [ ] 给 topic_echo.py 加 --from

Modify `src/lcm_tools/commands/topic_echo.py`:

(a) Add the option parameter (after `lcm_port`):

```python
    from_log: Optional[str] = typer.Option(
        None,
        "--from",
        help="Read from a .log file instead of live multicast (offline analysis).",
    ),
```

(b) Replace the `run_listener(...)` call (lines ~141-145) with source-based dispatch. Find:

```python
    stop_event = run_listener(
        _on_packet,
        mc_addr=lcm_url,
        mc_port=lcm_port,
    )
```

Replace with:

```python
    from lcm_tools.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
    )
    stop_event = source.start(_on_packet)
```

Leave the rest (queue, display loop, count/timeout) unchanged — `LogFileSource` delivers `PacketInfo` objects through the same `_on_packet` callback.

### Step 5.4: [ ] 运行 echo 测试确认通过

Run: `pytest tests/test_record.py::TestEchoFromLog -v`
Expected: PASS

### Step 5.5: [ ] 给 topic_stats.py 加 --from

Modify `src/lcm_tools/commands/topic_stats.py`: add the option (after `lcm_port`):

```python
    from_log: Optional[str] = typer.Option(
        None,
        "--from",
        help="Read from a .log file instead of live multicast.",
    ),
```

Replace the `run_listener(...)` call with:

```python
    from lcm_tools.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
        duration=duration,
    )
    stop_event = source.start(collector.on_packet)
```

> Note: pass `duration` into the source so LogFileSource stops at the right wall-clock point; the existing `while True` loop's own duration check remains and will also break the LiveTable.

### Step 5.6: [ ] 给 topic_list.py 加 --from

Modify `src/lcm_tools/commands/topic_list.py`: add the option (after `lcm_port`):

```python
    from_log: Optional[str] = typer.Option(
        None,
        "--from",
        help="Read from a .log file instead of live multicast.",
    ),
```

Replace the `run_listener(...)` + `time.sleep(duration)` block:

```python
    stop_event = run_listener(discovery.on_packet, mc_addr=lcm_url, mc_port=lcm_port)

    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
```

with:

```python
    from lcm_tools.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
        duration=duration,
    )
    stop_event = source.start(discovery.on_packet)

    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
```

### Step 5.7: [ ] 写 stats/list --from 集成测试

Append to `tests/test_record.py`:

```python
class TestStatsFromLog:
    def test_stats_reads_from_log_file(self, tmp_path):
        from lcm_tools.lcm_log import LogEvent, write_lcm_log
        from typer.testing import CliRunner

        from lcm_tools.cli import app

        events = [
            LogEvent(0, 1_000_000, "CAM", b"\x00" * 100),
            LogEvent(1, 1_000_100, "CAM", b"\x00" * 100),
            LogEvent(2, 1_000_200, "LIDAR", b"\x00" * 50),
        ]
        log_path = tmp_path / "demo.log"
        write_lcm_log(log_path, events)

        runner = CliRunner()
        result = runner.invoke(
            app, ["topic", "stats", "--from", str(log_path), "--duration", "0"]
        )
        assert result.exit_code == 0, result.output
        assert "CAM" in result.output
        assert "LIDAR" in result.output


class TestListFromLog:
    def test_list_reads_from_log_file(self, tmp_path):
        from lcm_tools.lcm_log import LogEvent, write_lcm_log
        from typer.testing import CliRunner

        from lcm_tools.cli import app

        events = [
            LogEvent(0, 1_000_000, "CAM", b"\x01"),
            LogEvent(1, 1_000_100, "LIDAR", b"\x02"),
        ]
        log_path = tmp_path / "demo.log"
        write_lcm_log(log_path, events)

        runner = CliRunner()
        result = runner.invoke(
            app, ["topic", "list", "--from", str(log_path), "--duration", "0"]
        )
        assert result.exit_code == 0, result.output
        assert "CAM" in result.output
        assert "LIDAR" in result.output
```

### Step 5.8: [ ] 运行所有 --from 测试确认通过

Run: `pytest tests/test_record.py -v`
Expected: PASS (all integration tests)

### Step 5.9: [ ] 提交

```bash
git add src/lcm_tools/commands/topic_echo.py src/lcm_tools/commands/topic_stats.py \
        src/lcm_tools/commands/topic_list.py tests/test_record.py
git commit -m "feat(commands): echo/stats/list 接入 --from 离线日志源"
```

---

## Task 6: 文档更新

**Files:**
- Modify: `README.md`
- Modify: `README_zh.md`

### Step 6.1: [ ] 更新 README.md

In `README.md`, add a new `## Recording & Replay` section after the `### Statistics` section (around line 121). Insert:

```markdown
## Recording & Replay

```bash
# Record all live channels to a timestamped .log file (Ctrl+C to stop)
lcm record

# Record to a specific file for 60 seconds, filtering channels
lcm record -o run.log --channel "CAM.*" --duration 60

# Replay a log to the multicast network at original speed
lcm play run.log

# Replay at half speed, looping
lcm play run.log --speed 0.5 --loop

# Analyze an offline log instead of live traffic (works with echo/stats/list)
lcm topic echo EXAMPLE --from run.log
lcm topic stats --from run.log
lcm topic list --from run.log
```

Logs are written in the standard LCM event-log format, fully compatible with `lcm-logger`, `lcm-logplayer`, and `lcm.EventLog`. No external dependencies required.
```

Also update the `## Features` block (near line 9) to add two lines:

```
lcm record <file.log>        — Record live traffic to a .log file (like lcm-logger)
lcm play <file.log>          — Replay a .log file to the network (like lcm-logplayer)
```

And add `--from <file.log>` mentions where echo/stats/list are described.

### Step 6.2: [ ] 更新 README_zh.md

Apply the equivalent Chinese-language additions to `README_zh.md` (record/play 章节 + Features 块). Match the existing bilingual tone of that file.

### Step 6.3: [ ] 提交

```bash
git add README.md README_zh.md
git commit -m "docs: 新增 record/play/--from 章节中英文说明"
```

---

## Task 7: 整体回归与自审

### Step 7.1: [ ] 全量测试

Run: `pytest tests/ -v`
Expected: ALL PASS (existing + new).

### Step 7.2: [ ] CLI 冒烟测试

Run these and confirm sane `--help` output and no errors:

```bash
lcm --help
lcm record --help
lcm play --help
lcm topic echo --help   # confirm --from appears
lcm topic stats --help  # confirm --from appears
lcm topic list --help   # confirm --from appears
```

### Step 7.3: [ ] 端到端冒烟(可选,需本地组播)

If a live multicast environment is available:

```bash
# Terminal 1: record
lcm record -o test.log --duration 5
# Terminal 2 (during the 5s): publish something
# Then: replay + offline stats
lcm play test.log &
lcm topic stats --from test.log
```

(If no multicast environment, rely on the unit/integration tests — they mock the socket layer.)

### Step 7.4: [ ] 最终提交(如有遗漏修正)

```bash
git add -A
git commit -m "test: A组录制/回放/离线源 全量回归"
```

---

## Self-Review 备注

- **Spec 覆盖**:record(§4.1)、play(§4.2)、echo/stats/list `--from`(§4.3)、lcm_log 格式(§3)、source 抽象(§2)、错误处理(§6 坏 sync word / 文件不存在由 typer/iter_lcm_log 覆盖)、测试(§7)、YAGNI 边界(§9 均不做)。✅
- **类型一致性**:`LogEvent(eventnum, timestamp_us, channel, data)` 在 Task 1/2/5 全部一致;`PacketSource.start(callback) -> threading.Event` 在 Task 2/5 一致;`make_source(from_path, ...)` 签名一致。✅
- **已知取舍**:record 现将事件全缓冲到内存再 flush(`write_lcm_log` 在 finally 调一次)。对长录制这是隐患——但 A 组首版优先简单,且 `write_lcm_log` 已设计为流式(可改为边录边写)。若 Task 7.1 测试发现内存问题,改为增量写。此项记录在案,不阻塞。
```
