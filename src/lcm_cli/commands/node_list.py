"""``lcm node list`` — discover and list publisher nodes.

LCM has no native "node name" concept (unlike ROS2).  This command
identifies publisher processes by their UDP source address (IP:port),
grouped with the set of channels each has published to.

This is a best-effort inference based on the multicast traffic that
reaches this host within a configurable listening window.
"""

from __future__ import annotations

from __future__ import annotations

import time

from typing import Optional

import typer
from rich.console import Console

from lcm_cli.core.discovery import ChannelDiscovery
from lcm_cli.display.stats_display import build_node_table
from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT

_console = Console()

# Typer sub-app for `lcm node`
node_app = typer.Typer(
    help="Inspect LCM publisher nodes (inferred from UDP source address).",
    no_args_is_help=True,
)


@node_app.command(name="list")
def list_nodes(
    duration: float = typer.Option(
        5.0,
        "--duration",
        "-d",
        help="How many seconds to listen for node activity.",
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
        10.0, "--stale", help="Seconds without messages to consider node stale."
    ),
) -> None:
    """List discovered publisher nodes (like ``ros2 node list``).

    Note: LCM does not have a native "node name" concept.  Nodes are
    identified here by their UDP source IP:port, which corresponds to
    the publisher's network interface.
    """
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
            f"[bold]Watching for nodes ...[/bold]  "
            f"(multicast: {lcm_url}:{lcm_port}, stale: {stale}s, Ctrl+C to stop)"
        )

        try:
            with Live(auto_refresh=False) as live:
                while True:
                    time.sleep(1.0)
                    nodes = discovery.get_nodes(stale_after=stale)
                    table = build_node_table(nodes)
                    live.update(table)
                    live.refresh()
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()
            nodes = discovery.get_nodes(stale_after=stale)
            if nodes:
                _console.print(build_node_table(nodes))
            else:
                _console.print("[yellow]No publisher nodes found.[/yellow]")
    else:
        # Existing snapshot behavior (backward compatible)
        _console.print(
            f"[bold]Discovering nodes for {duration}s ...[/bold]  "
            f"(multicast: {lcm_url}:{lcm_port})"
        )

        try:
            time.sleep(duration)
        except KeyboardInterrupt:
            pass
        finally:
            stop_event.set()

        nodes = discovery.get_nodes(stale_after=stale)
        if not nodes:
            _console.print("[yellow]No publisher nodes found.[/yellow]")
            _console.print(
                "[dim]Hint: make sure a publisher is running and your "
                "multicast routing is configured.[/dim]"
            )
            raise typer.Exit(code=0)

        _console.print(build_node_table(nodes))
