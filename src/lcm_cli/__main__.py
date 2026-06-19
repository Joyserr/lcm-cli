"""Allow running lcm_cli as `python -m lcm_cli`."""

from __future__ import annotations

from lcm_cli.cli import app

if __name__ == "__main__":
    app()
