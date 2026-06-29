"""``lcm dashboard`` — launch the LCM Dashboard web UI.

Starts a FastAPI web server that visualizes LCM data in real-time
or from a log file. Accessible from any browser on the network.
"""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from lcm_cli.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT

console = Console()


def dashboard(
    port: int = typer.Option(8080, "--port", "-p", help="HTTP server port."),
    bind: str = typer.Option("0.0.0.0", "--bind", "-b", help="Bind address (0.0.0.0 for remote access)."),
    from_log: Optional[str] = typer.Option(
        None, "--from", help="Replay from an LCM .log file instead of live multicast."
    ),
    lcm_files: Optional[List[str]] = typer.Option(
        None, "--lcm-file", "-f",
        help="Path to .lcm file or directory for type definitions. Can repeat.",
    ),
    lcm_url: str = typer.Option(DEFAULT_MC_ADDR, "--lcm-url", help="LCM multicast address."),
    lcm_port: int = typer.Option(DEFAULT_MC_PORT, "--lcm-port", help="LCM multicast port."),
) -> None:
    """Launch the LCM Dashboard web UI for real-time data visualization."""
    try:
        import uvicorn
    except ImportError:
        console.print(
            "[red]Dashboard dependencies not installed.[/red]\n"
            "Install with: [bold]pip install lcm-cli\\[dashboard][/bold]"
        )
        raise typer.Exit(code=1)

    from lcm_cli.dashboard.data_bridge import DataBridge
    from lcm_cli.dashboard.server import create_app
    from lcm_cli.source import make_source

    # Build type registry if --lcm-file provided
    type_registry = None
    if lcm_files:
        try:
            from lcm_cli.core.lcm_type_builder import TypeRegistry

            type_registry = TypeRegistry()
            type_registry.register_paths(lcm_files)
            n_types = len(type_registry.all_types)
            console.print(f"[green]Loaded {n_types} type(s) from {len(lcm_files)} path(s).[/green]")
        except Exception as exc:
            console.print(f"[red]Failed to load LCM files:[/red] {exc}")
            raise typer.Exit(code=1)

    bridge = DataBridge()
    if type_registry:
        bridge.set_type_registry(type_registry)

    # Create data source
    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
    )

    app = create_app(bridge=bridge, source=source)

    # Print startup info
    console.print(f"\n[bold green]LCM Dashboard[/bold green]")
    console.print(f"  URL: [bold]http://{bind}:{port}[/bold]")
    if from_log:
        console.print(f"  Source: Replaying [cyan]{from_log}[/cyan]")
    else:
        console.print(f"  Source: Live multicast [cyan]{lcm_url}:{lcm_port}[/cyan]")
    console.print(f"  Press Ctrl+C to stop.\n")

    # Start uvicorn — the FastAPI startup handler will set the bridge's
    # event loop and start the data source on the correct running loop.
    try:
        uvicorn.run(app, host=bind, port=port, log_level="info", ws="websockets")
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()
        console.print("\n[dim]Dashboard stopped.[/dim]")
