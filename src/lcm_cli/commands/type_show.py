"""``lcm type show`` — show detailed type structure."""

from __future__ import annotations

from typing import List, Optional

import typer
from rich.console import Console

from lcm_cli.core.lcm_type_builder import TypeRegistry
from lcm_cli.display.type_display import build_type_show_table

_console = Console()


def type_show(
    name: str = typer.Argument(..., help="Type name to show (e.g., mypkg.pose_t)."),
    lcm_files: Optional[List[str]] = typer.Option(
        None, "--lcm-file", "-f", help="Path to .lcm file or directory."
    ),
) -> None:
    """Show detailed structure of an LCM type."""
    if not lcm_files:
        _console.print("[red]Error:[/red] At least one --lcm-file required.")
        raise typer.Exit(code=1)

    registry = TypeRegistry()
    try:
        registry.register_paths(lcm_files)
    except Exception as exc:
        _console.print(f"[red]Failed to load LCM files:[/red] {exc}")
        raise typer.Exit(code=1)

    # Find the struct definition
    struct = None
    for s in registry._structs:
        if s.full_name == name or s.short_name == name:
            struct = s
            break

    if not struct:
        # Fuzzy match suggestion
        all_names = [s.full_name for s in registry._structs]
        suggestions = [n for n in all_names if name.lower() in n.lower()]
        _console.print(f"[red]Type '{name}' not found.[/red]")
        if suggestions:
            _console.print(f"Did you mean: {', '.join(suggestions[:3])}")
        raise typer.Exit(code=1)

    table = build_type_show_table(struct, registry)
    _console.print(table)
