"""Unified packet data-source abstraction.

Both the live multicast network and an offline LCM ``.log`` file expose the
same interface (``PacketSource``), so every consumer command can be agnostic
about where its packets come from. This is the structural backbone that the
``--from <file.log>`` option and the ``record``/``play`` commands build on.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional, Protocol

from lcm_cli.lcm_log import LogEvent, iter_lcm_log
from lcm_cli.listener import (
    DEFAULT_MC_ADDR,
    DEFAULT_MC_PORT,
    run_listener,
)
from lcm_cli.protocol import PacketInfo

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
            start_wall = time.monotonic()
            prev_ts_us: Optional[int] = None
            for ev in iter_lcm_log(self.path):
                if stop_event.is_set():
                    return
                if self.duration is not None and (
                    time.monotonic() - start_wall
                ) >= self.duration:
                    return
                if prev_ts_us is not None and self.speed > 0:
                    delta = (
                        (ev.timestamp_us - prev_ts_us)
                        / 1_000_000.0
                        / self.speed
                    )
                    if delta > 0:
                        self._sleep_interruptible(delta, stop_event)
                        if stop_event.is_set():
                            return
                prev_ts_us = ev.timestamp_us
                callback(self._event_to_packet(ev))

        t = threading.Thread(target=_worker, daemon=True, name="lcm-logsource")
        t.start()
        return stop_event

    @staticmethod
    def _sleep_interruptible(seconds: float, stop_event: threading.Event) -> None:
        """Sleep for *seconds*, waking promptly when stop_event is set.

        Uses time.sleep (monkeypatchable in tests) for the actual wait, but
        re-checks stop_event frequently so a stop request interrupts the sleep.
        """
        end = time.monotonic() + seconds
        while True:
            if stop_event.is_set():
                return
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(remaining, 0.05))

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
