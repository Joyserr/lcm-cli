"""Bridge between LCM data source and WebSocket subscribers.

Receives ``PacketInfo`` objects from the ``PacketSource`` callback,
decodes them using a ``TypeRegistry``, extracts numeric fields,
stores them in per-channel ``RingBuffer`` instances, and distributes
to WebSocket clients via ``asyncio.Queue``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Optional

from lcm_cli.dashboard.field_extractor import extract_numeric_fields, get_field_schema
from lcm_cli.dashboard.ring_buffer import RingBuffer
from lcm_cli.protocol import PacketInfo, extract_fingerprint

logger = logging.getLogger(__name__)


class DataBridge:
    """Receives LCM packets, decodes them, and distributes to subscribers."""

    def __init__(self, buffer_duration_sec: float = 300.0):
        self._buffer_duration = buffer_duration_sec
        self._buffers: dict[str, RingBuffer] = {}
        self._schemas: dict[str, list[dict[str, str]]] = {}
        self._channel_subs: dict[str, set[str]] = {}  # channel → set of ws_ids
        self._subscribers: dict[str, asyncio.Queue] = {}  # ws_id → queue
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[threading.Event] = None
        self._type_registry: Any = None  # TypeRegistry if provided

    @property
    def is_running(self) -> bool:
        return self._stop_event is not None and not self._stop_event.is_set()

    @property
    def subscriptions(self) -> dict[str, set[str]]:
        return self._channel_subs

    def set_type_registry(self, registry: Any) -> None:
        """Set the TypeRegistry for fingerprint-based auto-decode."""
        self._type_registry = registry

    # -- Subscriber management --

    def add_subscriber(
        self,
        ws_id: str,
        channels: list[str],
        fields: list[str] | None = None,
    ) -> None:
        for ch in channels:
            self._channel_subs.setdefault(ch, set()).add(ws_id)

    def remove_subscriber(self, ws_id: str) -> None:
        for ch in list(self._channel_subs.keys()):
            self._channel_subs[ch].discard(ws_id)
            if not self._channel_subs[ch]:
                del self._channel_subs[ch]
        self._subscribers.pop(ws_id, None)

    def register_ws_queue(self, ws_id: str, queue: asyncio.Queue) -> None:
        self._subscribers[ws_id] = queue

    # -- Packet processing (called from source callback thread) --

    def on_packet(self, pkt: PacketInfo) -> None:
        """Callback invoked by PacketSource for each received packet."""
        if not pkt.has_channel or pkt.channel is None:
            return

        channel = pkt.channel
        timestamp = time.time()

        # Try to decode using TypeRegistry
        decoded = self._try_decode(pkt)
        if decoded is None:
            return  # Skip undecodable packets

        fields = extract_numeric_fields(decoded)
        if not fields:
            return

        # Cache schema on first decoded message
        if channel not in self._schemas:
            self._schemas[channel] = get_field_schema(decoded)

        # Store in ring buffer
        if channel not in self._buffers:
            self._buffers[channel] = RingBuffer(self._buffer_duration)
        self._buffers[channel].append(timestamp, fields)

        # Distribute to subscribers
        msg = {"channel": channel, "timestamp": timestamp, "data": fields}
        for ws_id in self._channel_subs.get(channel, set()):
            queue = self._subscribers.get(ws_id)
            if queue and self._loop and not self._loop.is_closed():
                try:
                    self._loop.call_soon_threadsafe(queue.put_nowait, msg)
                except Exception:
                    pass  # Queue might be gone if client disconnected

    def _try_decode(self, pkt: PacketInfo) -> Any:
        """Attempt to decode the packet payload using the type registry."""
        if self._type_registry is None:
            return None
        fp = extract_fingerprint(pkt.payload)
        if fp is None:
            return None
        decode_cls = self._type_registry.find_by_fingerprint(fp)
        if decode_cls is None:
            return None
        try:
            return decode_cls.decode(pkt.payload)
        except Exception as exc:
            logger.debug("Decode failed for %s: %s", pkt.channel, exc)
            return None

    # -- Query API (called from FastAPI request handlers) --

    def get_channels(self) -> list[str]:
        return sorted(self._buffers.keys())

    def get_schema(self, channel: str) -> list[dict[str, str]] | None:
        return self._schemas.get(channel)

    def get_history(
        self,
        channel: str,
        fields: list[str],
        t_start: float | None = None,
        t_end: float | None = None,
    ) -> dict[str, list]:
        buf = self._buffers.get(channel)
        if not buf:
            return {f: [] for f in fields}
        return buf.get_fields(fields)

    # -- Lifecycle --

    def start(
        self,
        source: Any,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Start consuming packets from a PacketSource."""
        self._loop = loop
        self._stop_event = source.start(self.on_packet)

    def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
