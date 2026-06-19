"""``lcm topic list`` — discover and list active LCM channels.

Joins the LCM multicast group, listens for a configurable duration,
and prints a table of all observed channels with their message counts,
total sizes, and publisher addresses.
"""

from __future__ import annotations

from __future__ import annotations

import time

from typing import Optional

import typer
from rich.console import Console

from lcm_cli.core.discovery import ChannelDiscovery
from lcm_cli.display.stats_display import build_channel_table
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT

_console = Console()


def list_channels(
    duration: float = typer.Option(
        5.0,
        "--duration",
        "-d",
        help="How many seconds to listen for channel activity.",
    ),
    lcm_url: str = typer.Option(
        DEFAULT_MC_ADDR,
        "--lcm-url",
        help="LCM multicast address.",
    ),
    lcm_port: int = typer.Option(
        DEFAULT_MC_PORT,
        "--lcm-port",
        help="LCM multicast port.",
    ),
    from_log: Optional[str] = typer.Option(
        None,
        "--from",
        help="Read from a .log file instead of live multicast.",
    ),
    watch: bool = typer.Option(
        False, "--watch", help="Continuous refresh mode (Live table)."
    ),
    stale: float = typer.Option(
        10.0, "--stale", help="Seconds without messages to consider channel stale."
    ),
) -> None:
    """List active LCM channels (like ``ros2 topic list``)."""
    discovery = ChannelDiscovery()

    # Use PacketSource for live/offline
    from lcm_cli.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
        duration=duration if not watch else None,
    )
    stop_event = source.start(discovery.on_packet)

    if watch:
        # Continuous LIVE table mode
        from rich.live import Live

        _console.print(
            f"[bold]Watching for channels ...[/bold]  "
            f"(multicast: {lcm_url}:{lcm_port}, stale: {stale}s, Ctrl+C to stop)"
        )

        try:
            with Live(auto_refresh=False) as live:
                while True:
                    time.sleep(1.0)
                    active = discovery.get_active_channels(stale_after=stale)
                    table = build_channel_table(active)
                    live.update(table)
                    live.refresh()
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            # Print final snapshot
            active = discovery.get_active_channels(stale_after=stale)
            if active:
                _console.print(build_channel_table(active))
            else:
                _console.print("[yellow]No active channels found.[/yellow]")
    else:
        # Existing snapshot behavior (backward compatible)
        _console.print(
            f"[bold]Discovering channels for {duration}s ...[/bold]  "
            f"(multicast: {lcm_url}:{lcm_port})"
        )

        try:
            time.sleep(duration)
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()

        channels = discovery.get_active_channels(stale_after=stale)
        if not channels:
            _console.print("[yellow]No active channels found.[/yellow]")
            _console.print(
                "[dim]Hint: make sure a publisher is running and your "
                "multicast routing is configured.[/dim]"
            )
            raise typer.Exit(code=0)

        _console.print(build_channel_table(channels))
