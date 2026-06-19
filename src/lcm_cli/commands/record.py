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

import typer
from rich.console import Console

from lcm_cli.lcm_log import LogEvent, write_lcm_log
from lcm_cli.listener import run_listener
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT, PacketInfo

_console = Console()


def _default_filename() -> str:
    return f"lcm_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"


def record(
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output .log file. Default: lcm_<YYYYMMDD_HHMMSS>.log",
    ),
    channel: str | None = typer.Option(
        None,
        "--channel",
        help="Regex to filter channels (e.g. 'CAM.*'). Default: record all.",
    ),
    duration: float | None = typer.Option(
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
    events: list[LogEvent] = []
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
