"""Rich Live table display for ``lcm topic stats`` and ``lcm topic list``.

Uses ``rich.live.Live`` to render a continuously updating table of
per-channel statistics in the terminal.
"""

from __future__ import annotations

from __future__ import annotations

from typing import List, Optional

from rich.console import Console
from rich.table import Table

from lcm_cli.core.discovery import ChannelInfo, NodeInfo
from lcm_cli.core.stats import StatsSnapshot

_console = Console()

# Sparkline Unicode block characters
_SPARKLINE_CHARS = "▁▂▃▄▅▆▇█"


def build_stats_table(
    snap: StatsSnapshot,
    sort_by: str = "name",
    top_n: Optional[int] = None,
    show_sparkline: bool = False,
) -> Table:
    """Build a Rich Table from a stats snapshot.

    Args:
        snap: Statistics snapshot.
        sort_by: Sort key ('name', 'rate', 'bw', 'msgs').
        top_n: Show only top N channels.
        show_sparkline: Whether to show bandwidth sparkline column.
    """
    table = Table(
        title="LCM Channel Statistics",
        show_lines=False,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Channel", style="cyan", min_width=18)
    table.add_column("Messages", justify="right", style="bold")
    table.add_column("Rate (Hz)", justify="right", style="green")
    table.add_column("BW (KB/s)", justify="right", style="yellow")
    table.add_column("Avg Size (B)", justify="right")
    table.add_column("Total (KB)", justify="right", style="blue")

    if show_sparkline:
        table.add_column("BW Trend", justify="center")

    # Sort channels
    channels = list(snap.channels)
    if sort_by == "rate":
        channels.sort(key=lambda c: c.frequency_hz, reverse=True)
    elif sort_by == "bw":
        channels.sort(key=lambda c: c.bandwidth_kbps, reverse=True)
    elif sort_by == "msgs":
        channels.sort(key=lambda c: c.msg_count, reverse=True)
    # 'name' is default order (already sorted)

    # Apply top N limit
    if top_n is not None:
        channels = channels[:top_n]

    for ch in channels:
        row_data = [
            ch.channel,
            str(ch.msg_count),
            f"{ch.frequency_hz:.1f}",
            f"{ch.bandwidth_kbps:.2f}",
            f"{ch.avg_msg_size:.0f}",
            f"{ch.total_bytes / 1024:.1f}",
        ]
        if show_sparkline:
            spark = _render_sparkline(getattr(ch, "bw_history", []))
            row_data.append(spark)
        table.add_row(*row_data)

    # Summary row
    table.add_section()
    table.add_row(
        f"[bold]{snap.total_channels} channels[/bold]",
        f"[bold]{snap.total_messages}[/bold]",
        "",
        f"[bold]{snap.total_bandwidth_kbps:.2f}[/bold]",
        "",
        f"[bold]{snap.total_bytes / 1024:.1f}[/bold]",
    )
    return table


def _render_sparkline(values: List[float]) -> str:
    """Render a list of values as a sparkline string.

    Args:
        values: List of numeric values (e.g., bandwidth samples).

    Returns:
        Unicode sparkline string.
    """
    if not values or len(values) < 2:
        return "-"

    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return _SPARKLINE_CHARS[4] * min(len(values), 10)

    range_val = max_val - min_val
    num_buckets = len(_SPARKLINE_CHARS)

    spark_chars = []
    for v in values[-10:]:  # Show last 10 samples max
        bucket = int((v - min_val) / range_val * (num_buckets - 1))
        bucket = min(bucket, num_buckets - 1)
        spark_chars.append(_SPARKLINE_CHARS[bucket])

    return "".join(spark_chars)


def build_bw_table(
    snap: StatsSnapshot,
    show_sparkline: bool = False,
) -> Table:
    """Build a bandwidth-focused table for a single channel.

    Args:
        snap: Statistics snapshot (should contain only one channel).
        show_sparkline: Whether to show bandwidth sparkline.
    """
    table = Table(
        title="LCM Bandwidth Monitor",
        show_lines=False,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Channel", style="cyan", min_width=18)
    table.add_column("Rate (Hz)", justify="right", style="green")
    table.add_column("BW (KB/s)", justify="right", style="yellow")
    table.add_column("Avg Size (B)", justify="right")
    table.add_column("Total (KB)", justify="right", style="blue")

    if show_sparkline:
        table.add_column("BW Trend", justify="center")

    for ch in snap.channels:
        row_data = [
            ch.channel,
            f"{ch.frequency_hz:.1f}",
            f"{ch.bandwidth_kbps:.2f}",
            f"{ch.avg_msg_size:.0f}",
            f"{ch.total_bytes / 1024:.1f}",
        ]
        if show_sparkline:
            spark = _render_sparkline(getattr(ch, "bw_history", []))
            row_data.append(spark)
        table.add_row(*row_data)

    return table


def build_channel_table(channels: List[ChannelInfo]) -> Table:
    """Build a Rich Table listing discovered channels."""
    table = Table(
        title=f"Active LCM Channels ({len(channels)} found)",
        show_lines=False,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Channel", style="cyan", min_width=18)
    table.add_column("Messages", justify="right")
    table.add_column("Total Size", justify="right", style="blue")
    table.add_column("Publishers", justify="right", style="dim")

    for ch in channels:
        table.add_row(
            ch.name,
            str(ch.msg_count),
            f"{ch.total_bytes / 1024:.1f} KB",
            ", ".join(sorted(ch.publishers)) if ch.publishers else "-",
        )
    return table


def build_node_table(nodes: List[NodeInfo]) -> Table:
    """Build a Rich Table listing discovered publisher nodes."""
    table = Table(
        title=f"LCM Publisher Nodes ({len(nodes)} found)",
        show_lines=False,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Node (IP:port)", style="cyan", min_width=22)
    table.add_column("Channels", style="green")
    table.add_column("Messages", justify="right")
    table.add_column("Total Size", justify="right", style="blue")

    for node in nodes:
        channels_str = ", ".join(sorted(node.channels)) or "-"
        table.add_row(
            node.address,
            channels_str,
            str(node.msg_count),
            f"{node.total_bytes / 1024:.1f} KB",
        )
    return table
