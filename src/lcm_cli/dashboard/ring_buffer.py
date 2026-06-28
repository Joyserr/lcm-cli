"""Per-channel circular buffer with time-based eviction."""

from __future__ import annotations

from collections import deque
from typing import Any


class RingBuffer:
    """Stores (timestamp, data_dict) pairs, evicting entries older than max_duration_sec."""

    def __init__(self, max_duration_sec: float = 300.0):
        self._max_duration = max_duration_sec
        self._buffer: deque[tuple[float, dict[str, Any]]] = deque()

    def append(self, timestamp: float, data: dict[str, Any]) -> None:
        self._buffer.append((timestamp, data))
        self._evict(timestamp)

    def get_all(self) -> list[tuple[float, dict[str, Any]]]:
        return list(self._buffer)

    def get_range(
        self, t_start: float, t_end: float
    ) -> list[tuple[float, dict[str, Any]]]:
        return [(ts, d) for ts, d in self._buffer if t_start <= ts <= t_end]

    def get_fields(
        self, fields: list[str]
    ) -> dict[str, list[tuple[float, Any]]]:
        result: dict[str, list[tuple[float, Any]]] = {f: [] for f in fields}
        for ts, data in self._buffer:
            for f in fields:
                if f in data:
                    result[f].append((ts, data[f]))
        return result

    def _evict(self, now: float) -> None:
        cutoff = now - self._max_duration
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()
