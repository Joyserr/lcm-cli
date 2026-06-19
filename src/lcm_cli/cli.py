"""LCM CLI - ROS2-like command line tools for LCM middleware.

Provides the ``lcm`` command with subcommands:
  lcm topic echo <channel>   — View real-time topic data
  lcm topic list             — List active topics (channels)
  lcm topic stats            — Monitor topic statistics
  lcm node list              — List discovered publisher nodes
"""

from __future__ import annotations

from __future__ import annotations

import typer

from lcm_cli import __version__
from lcm_cli.commands.node_list import node_app
from lcm_cli.commands.play import play
from lcm_cli.commands.record import record
from lcm_cli.commands.topic_bw import bw
from lcm_cli.commands.topic_echo import echo
from lcm_cli.commands.topic_info import info
from lcm_cli.commands.topic_list import list_channels
from lcm_cli.commands.topic_stats import stats
from lcm_cli.commands.type_list import type_list
from lcm_cli.commands.type_show import type_show

# ---------------------------------------------------------------------------
# Root application
# ---------------------------------------------------------------------------
def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        typer.echo(f"lcm-cli {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="lcm",
    help="LCM command line tools — inspect and monitor LCM networks.\n\n"
    "Similar to ROS2 CLI tools (ros2 topic echo, ros2 node list, etc.) "
    "but for LCM (Lightweight Communications and Marshalling).",
    no_args_is_help=True,
    add_completion=True,  # Enable shell completion
)

# Add --version option
@app.callback()
def main_callback(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit."
    ),
) -> None:
    """LCM CLI tools."""
    pass

# ---------------------------------------------------------------------------
# Topic subcommand group
# ---------------------------------------------------------------------------
topic_app = typer.Typer(
    help="Inspect and monitor LCM topics (channels).",
    no_args_is_help=True,
)
app.add_typer(topic_app, name="topic")

# Register topic subcommands
topic_app.command(name="echo", help="Echo messages on a channel.")(echo)
topic_app.command(name="list", help="List active channels.")(list_channels)
topic_app.command(name="stats", help="Show real-time channel statistics.")(stats)
topic_app.command(name="bw", help="Monitor bandwidth for a channel.")(bw)
topic_app.command(name="info", help="Show detailed channel information.")(info)

# Node subcommand group is imported as a Typer app and attached directly
app.add_typer(node_app, name="node")

# Type subcommand group
type_app = typer.Typer(
    help="Inspect LCM type definitions.",
    no_args_is_help=True,
)
app.add_typer(type_app, name="type")

type_app.command(name="list", help="List registered types.")(type_list)
type_app.command(name="show", help="Show type structure.")(type_show)

# Top-level standalone commands (record/play mirror `ros2 bag record/play`)
app.command(name="record", help="Record live LCM traffic to a .log file.")(record)
app.command(name="play", help="Replay an LCM .log file to the multicast network.")(play)


if __name__ == "__main__":
    app()
