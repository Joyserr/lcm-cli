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
