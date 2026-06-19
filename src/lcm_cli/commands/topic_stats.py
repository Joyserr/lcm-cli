"""``lcm topic stats`` — real-time per-channel statistics monitor.

Joins the LCM multicast group and displays a continuously updating
table of message frequency, bandwidth, message sizes, and cumulative
data transfer for each observed channel.
"""

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.live import Live

from lcm_cli.core.stats import StatsCollector
from lcm_cli.display.stats_display import build_stats_table
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT

_console = Console()


def stats(
    channel: str | None = typer.Argument(
        None,
        help="Only monitor channels whose name contains this string. "
        "Leave empty to monitor all channels.",
    ),
    duration: float | None = typer.Option(
        None,
        "--duration",
        "-d",
        help="Stop after this many seconds. "
        "Default: run until Ctrl+C.",
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
    from_log: str | None = typer.Option(
        None,
        "--from",
        help="Read from a .log file instead of live multicast.",
    ),
    sort_by: str = typer.Option(
        "name",
        "--sort",
        help="Sort by: name (default), rate, bw, msgs",
    ),
    top_n: int | None = typer.Option(
        None,
        "--top",
        help="Show only top N channels",
    ),
    freeze: bool = typer.Option(
        False,
        "--freeze",
        help="Capture one snapshot and exit",
    ),
    spark: bool = typer.Option(
        False,
        "--spark",
        help="Show bandwidth sparkline trend column",
    ),
) -> None:
    """Show real-time channel statistics (like ``ros2 topic hz``)."""
    # Validate sort_by
    valid_sort_keys = {"name", "rate", "bw", "msgs"}
    if sort_by not in valid_sort_keys:
        _console.print(f"[red]Invalid sort key:[/red] {sort_by}")
        _console.print(f"Valid options: {', '.join(sorted(valid_sort_keys))}")
        raise typer.Exit(code=1)

    collector = StatsCollector(channel_filter=channel)

    filter_label = f"matching '{channel}'" if channel else "all"
    _console.print(
        f"[bold]Collecting stats for {filter_label} channels ...[/bold]  "
        f"(multicast: {lcm_url}:{lcm_port}, Ctrl+C to stop)"
    )

    # Use PacketSource for live/offline
    from lcm_cli.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
        duration=duration,
    )
    stop_event = source.start(collector.on_packet)

    # Handle --freeze mode (one-shot snapshot)
    if freeze:
        time.sleep(2)  # Let collector gather some data
        snap = collector.snapshot()
        table = build_stats_table(
            snap,
            sort_by=sort_by,
            top_n=top_n,
            show_sparkline=spark,
        )
        _console.print(table)
        stop_event.set()
        return

    start_time = time.monotonic()

    try:
        with Live(
            build_stats_table(
                collector.snapshot(),
                sort_by=sort_by,
                top_n=top_n,
                show_sparkline=spark,
            ),
            console=_console,
            refresh_per_second=2,
        ) as live:
            while True:
                time.sleep(0.5)
                live.update(
                    build_stats_table(
                        collector.snapshot(),
                        sort_by=sort_by,
                        top_n=top_n,
                        show_sparkline=spark,
                    )
                )

                if duration and (time.monotonic() - start_time) >= duration:
                    break

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()

    # Print final snapshot
    _console.print("\n[bold]Final Statistics:[/bold]")
    _console.print(build_stats_table(collector.snapshot()))
