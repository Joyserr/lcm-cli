"""``lcm play`` — replay a standard LCM ``.log`` file to the multicast network.

Reads events in file order and re-publishes each on the multicast group as a
fresh LCM short-message datagram, spacing them by their original timestamp
delta (scaled by ``--speed``). This is the counterpart to ``lcm record`` and
is wire-compatible with logs produced by ``lcm-logger``.
"""

from __future__ import annotations

from __future__ import annotations

import re
import socket
import struct
import time

import typer
from rich.console import Console

from lcm_cli.lcm_log import iter_lcm_log
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT, LCM2_MAGIC_SHORT

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
    channel: str | None = typer.Option(
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
            prev_ts_us: int | None = None
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
