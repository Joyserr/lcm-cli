"""``lcm type list`` — list registered LCM types."""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from lcm_tools.core.lcm_type_builder import TypeRegistry
from lcm_tools.display.type_display import build_type_list_table

_console = Console()


def type_list(
    lcm_files: Optional[List[str]] = typer.Option(
        None, "--lcm-file", "-f", help="Path to .lcm file or directory."
    ),
    package: Optional[str] = typer.Option(
        None, "--package", help="Filter by package name."
    ),
    grep: Optional[str] = typer.Option(
        None, "--grep", help="Filter by type name substring."
    ),
) -> None:
    """List registered LCM types."""
    if not lcm_files:
        _console.print("[red]Error:[/red] At least one --lcm-file required.")
        raise typer.Exit(code=1)

    registry = TypeRegistry()
    try:
        registry.register_paths(lcm_files)
    except Exception as exc:
        _console.print(f"[red]Failed to load LCM files:[/red] {exc}")
        raise typer.Exit(code=1)

    table = build_type_list_table(registry, package_filter=package, grep_filter=grep)
    _console.print(table)
