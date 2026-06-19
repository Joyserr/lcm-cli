"""``lcm topic bw`` — monitor bandwidth for a single channel."""

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.live import Live

from lcm_cli.core.stats import StatsCollector
from lcm_cli.display.stats_display import build_bw_table
from lcm_cli.listener import run_listener
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT

_console = Console()


def bw(
    channel: str = typer.Argument(..., help="Channel name to monitor."),
    window: float = typer.Option(
        5.0, "--window", "-w", help="Sliding window size in seconds."
    ),
    spark: bool = typer.Option(False, "--spark", help="Show BW trend sparkline."),
    lcm_url: str = typer.Option(DEFAULT_MC_ADDR, "--lcm-url"),
    lcm_port: int = typer.Option(DEFAULT_MC_PORT, "--lcm-port"),
) -> None:
    """Monitor bandwidth for a single LCM channel (like ``ros2 topic bw``)."""
    collector = StatsCollector()

    def _on_packet(pkt):
        if pkt.has_channel and pkt.channel == channel:
            collector.on_packet(pkt)

    stop_event = run_listener(_on_packet, mc_addr=lcm_url, mc_port=lcm_port)

    _console.print(
        f"[bold]Monitoring[/bold] [cyan]{channel}[/cyan]  "
        f"(window: {window}s, Ctrl+C to stop)"
    )

    try:
        with Live(auto_refresh=False) as live:
            while True:
                time.sleep(1.0)
                snap = collector.snapshot()
                table = build_bw_table(snap, show_sparkline=spark)
                live.update(table)
                live.refresh()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        # Print final snapshot
        snap = collector.snapshot()
        table = build_bw_table(snap, show_sparkline=spark)
        _console.print(table)
