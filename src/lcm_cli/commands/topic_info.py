"""``lcm topic info`` — display detailed information about an LCM channel.

Shows message statistics, type information (if available), bandwidth,
and publisher details for a specific channel.
"""

from __future__ import annotations

from __future__ import annotations

import time

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lcm_cli.display.type_display import build_type_show_table
from lcm_cli.core.lcm_type_builder import TypeRegistry
from lcm_cli.core.stats import StatsCollector
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT, fingerprint_to_hex

_console = Console()


def info(
    channel: str = typer.Argument(..., help="Channel name to inspect."),
    duration: float = typer.Option(
        3.0, "--duration", "-d", help="Seconds to observe the channel."
    ),
    lcm_url: str = typer.Option(
        DEFAULT_MC_ADDR, "--lcm-url", help="LCM multicast address."
    ),
    lcm_port: int = typer.Option(
        DEFAULT_MC_PORT, "--lcm-port", help="LCM multicast port."
    ),
    from_log: str | None = typer.Option(
        None, "--from", help="Read from a .log file instead of live multicast."
    ),
    lcm_file: str | None = typer.Option(
        None,
        "--lcm-file",
        help="Path to a single .lcm type file to pre-load into the registry.",
    ),
    lcm_dir: str | None = typer.Option(
        None,
        "--lcm-dir",
        help="Directory containing .lcm type files to pre-load into the registry.",
    ),
) -> None:
    """Display detailed information about a specific LCM channel."""
    # Build type registry
    type_registry: TypeRegistry | None = None
    if lcm_file or lcm_dir:
        type_registry = TypeRegistry()
        if lcm_file:
            type_registry.register_file(lcm_file)
            _console.print(f"[dim]Loaded type from: {lcm_file}[/dim]")
        if lcm_dir:
            type_registry.register_dir(lcm_dir)
            _console.print(f"[dim]Loaded types from: {lcm_dir}[/dim]")

    # Collect stats using the collector directly
    from lcm_cli.protocol import PacketInfo

    collector = StatsCollector()

    _console.print(f"[bold]Inspecting[/bold] [cyan]{channel}[/cyan]")
    _console.print()

    def _on_packet(pkt: PacketInfo) -> None:
        """Callback to collect stats."""
        if pkt.has_channel and pkt.channel == channel:
            collector.on_packet(pkt)

    # Use PacketSource abstraction for live or offline
    from lcm_cli.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
        duration=duration,
    )
    stop_event = source.start(_on_packet)

    # Wait for the specified duration (LiveSource ignores duration parameter)
    try:
        start_time = time.monotonic()
        while (time.monotonic() - start_time) < duration:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()

    snap = collector.snapshot()

    # Check if channel was found
    if not snap.channels:
        _console.print(f"[yellow]No messages observed for channel '{channel}'[/yellow]")
        raise typer.Exit(code=1)

    ch = snap.channels[0]

    # Build info panel
    info_table = Table(show_header=False, box=None, padding=(0, 1))
    info_table.add_column("Property", style="bold cyan")
    info_table.add_column("Value")

    info_table.add_row("Channel", channel)
    info_table.add_row("Messages", str(ch.msg_count))
    info_table.add_row("Total Size", f"{ch.total_bytes / 1024:.2f} KB")
    info_table.add_row("Avg Msg Size", f"{ch.avg_msg_size:.1f} bytes")
    info_table.add_row("Bandwidth", f"{ch.bandwidth_kbps:.2f} Kbps")
    info_table.add_row("Rate", f"{ch.frequency_hz:.1f} Hz")

    # Type information
    if ch.fingerprint is not None:
        fp_hex = fingerprint_to_hex(ch.fingerprint)
        info_table.add_row("Fingerprint", fp_hex)
        if type_registry:
            type_cls = type_registry.find_by_fingerprint(ch.fingerprint)
            if type_cls:
                info_table.add_row("Type", f"[green]{type_cls.__name__}[/green]")
                
                # Show type structure if available
                struct = None
                for s in type_registry._structs:
                    if s.full_name == type_cls.__name__ or s.short_name == type_cls.__name__:
                        struct = s
                        break
                if struct:
                    _console.print(Panel(info_table, title="Channel Info"))
                    _console.print()
                    type_table = build_type_show_table(struct, type_registry)
                    _console.print(type_table)
                    return

    _console.print(Panel(info_table, title="Channel Info"))
