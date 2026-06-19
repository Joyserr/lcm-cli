"""``lcm topic echo`` — echo messages received on a channel.

Listens on the LCM multicast group and prints every message matching
the given channel name (or pattern).

Supports four display modes:
- **default**: Rich panel with hex dump and metadata
- **--raw**: compact one-line-per-message text
- **--type module.Class**: decode payload with an lcm-gen generated class
- **--lcm-file path.lcm**: auto-decode from .lcm file definitions
"""

from __future__ import annotations

import queue
import re
import sys
import time
import typing

import typer
from rich.console import Console

from lcm_tools.display.echo_display import (
    echo_packet_auto_decode,
    echo_packet_decoded,
    echo_packet_default,
    echo_packet_raw,
    load_decode_class,
)
from lcm_tools.protocol import DEFAULT_MC_ADDR, DEFAULT_MC_PORT, PacketInfo, extract_fingerprint

_console = Console()


def echo(
    channel: str = typer.Argument(
        ...,
        help="Channel name to listen on. Use a regex pattern to match "
        "multiple channels (e.g. 'CAM.*').",
    ),
    count: int | None = typer.Option(
        None,
        "--count",
        "-n",
        help="Stop after receiving this many messages.",
    ),
    timeout: float | None = typer.Option(
        None,
        "--timeout",
        "-t",
        help="Stop after this many seconds with no matching messages.",
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Compact raw-text output (suitable for piping).",
    ),
    type_path: str | None = typer.Option(
        None,
        "--type",
        help="lcm-gen type for decoding, e.g. 'exlcm.example_t'. "
        "With --lcm-file, use just the struct name (e.g. 'example_t').",
    ),
    lcm_files: list[str] | None = typer.Option(
        None,
        "--lcm-file",
        "-f",
        help="Path to .lcm file or directory containing .lcm files. "
        "Can be specified multiple times. Enables auto-decode without lcm-gen.",
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
        help="Read from a .log file instead of live multicast (offline analysis).",
    ),
    csv_output: str | None = typer.Option(
        None,
        "--csv",
        help="Export decoded messages to CSV file.",
    ),
    jsonl_output: str | None = typer.Option(
        None,
        "--jsonl",
        help="Export decoded messages to JSON Lines file.",
    ),
    fields: list[str] | None = typer.Option(
        None,
        "--field",
        help="Extract specific fields (e.g. 'position[0]', 'imu.accel.x'). Can repeat.",
    ),
    ts_format: str = typer.Option(
        "epoch",
        "--ts-format",
        help="Timestamp format: epoch (default), iso, or lcm (microseconds).",
    ),
) -> None:
    """Echo messages on an LCM channel (like ``ros2 topic echo``)."""
    # Validate mutually exclusive options
    if csv_output and jsonl_output:
        _console.print("[red]Error:[/red] --csv and --jsonl are mutually exclusive.")
        raise typer.Exit(code=1)

    if fields and raw:
        _console.print("[red]Error:[/red] --field cannot be used with --raw.")
        raise typer.Exit(code=1)

    if fields and not type_path and not lcm_files:
        _console.print("[red]Error:[/red] --field requires --lcm-file or --type for decoding.")
        raise typer.Exit(code=1)

    # Parse field paths if provided
    field_paths = []
    if fields:
        try:
            from lcm_tools.export import FieldPath

            field_paths = [FieldPath.parse(f) for f in fields]
        except ValueError as exc:
            _console.print(f"[red]Invalid field path:[/red] {exc}")
            raise typer.Exit(code=1)
    # Compile channel filter
    try:
        pattern = re.compile(channel)
    except re.error as exc:
        _console.print(f"[red]Invalid regex pattern:[/red] {exc}")
        raise typer.Exit(code=1)

    # Build TypeRegistry from --lcm-file if provided
    type_registry: typing.Any = None
    if lcm_files:
        try:
            from lcm_tools.core.lcm_type_builder import TypeRegistry

            type_registry = TypeRegistry()
            type_registry.register_paths(lcm_files)
            n_types = len(type_registry.all_types)
            _console.print(
                f"[green]Loaded {n_types} type(s) from "
                f"{len(lcm_files)} LCM file path(s).[/green]"
            )
        except Exception as exc:
            _console.print(f"[red]Failed to load LCM files:[/red] {exc}")
            raise typer.Exit(code=1)

    # Resolve decode class
    decode_cls: typing.Any = None
    if type_path:
        if type_registry is not None:
            # Look up from registry (--lcm-file + --type)
            decode_cls = type_registry.find_by_name(type_path)
            if decode_cls is None:
                available = ", ".join(sorted(type_registry.all_types.keys()))
                _console.print(
                    f"[red]Type '{type_path}' not found in LCM files.[/red]\n"
                    f"Available: {available}"
                )
                raise typer.Exit(code=1)
        else:
            # Traditional: import from PYTHONPATH
            try:
                decode_cls = load_decode_class(type_path)
            except Exception as exc:
                _console.print(f"[red]Failed to load type '{type_path}':[/red] {exc}")
                raise typer.Exit(code=1)

    # Thread-safe queue bridging the listener thread → main display thread
    pkt_queue: "queue.Queue[PacketInfo | None]" = queue.Queue(maxsize=5000)

    def _on_packet(pkt: PacketInfo) -> None:
        if pkt.has_channel and pattern.search(pkt.channel):  # type: ignore[arg-type]
            try:
                pkt_queue.put_nowait(pkt)
            except queue.Full:
                pass  # drop oldest if producer outpaces display

    # Use PacketSource abstraction for live or offline
    from lcm_tools.source import make_source

    source = make_source(
        from_path=from_log,
        mc_addr=lcm_url,
        mc_port=lcm_port,
    )
    stop_event = source.start(_on_packet)

    _console.print(
        f"[bold]Listening on '{channel}' ...[/bold]  "
        f"(multicast: {lcm_url}:{lcm_port}, Ctrl+C to stop)"
    )

    # Initialize export writers if needed
    csv_writer = None
    jsonl_writer = None
    is_export_mode = csv_output or jsonl_output

    if is_export_mode:
        # Disable rich output for clean export
        _console.print(
            "[dim]Export mode active (no terminal display). Progress on stderr.[/dim]"
        )

        if csv_output:
            from lcm_tools.export import CsvWriter

            csv_file = open(csv_output, "w", newline="")
            csv_writer = CsvWriter(csv_file)

        if jsonl_output:
            from lcm_tools.export import JsonlWriter

            jsonl_file = open(jsonl_output, "w")
            jsonl_writer = JsonlWriter(jsonl_file)

    received = 0

    last_match_time = time.monotonic()

    try:
        while True:
            try:
                pkt = pkt_queue.get(timeout=0.3)
            except queue.Empty:
                if timeout and (time.monotonic() - last_match_time) >= timeout:
                    break
                continue

            if pkt is None:
                break

            received += 1
            last_match_time = time.monotonic()

            # Export mode: decode and write to file
            if is_export_mode and (csv_writer or jsonl_writer):
                decoded_obj = None
                timestamp = time.time()

                # Try to decode if we have type info
                if type_registry is not None:
                    fp = extract_fingerprint(pkt.payload)
                    if fp is not None:
                        decode_cls = type_registry.find_by_fingerprint(fp)
                        if decode_cls:
                            try:
                                decoded_obj = decode_cls.decode(pkt.payload)
                            except Exception:
                                pass  # Skip decode errors in export mode

                # Build export data
                export_data: typing.Dict[str, typing.Any] = {}

                # Timestamp
                if ts_format == "iso":
                    from datetime import datetime

                    export_data["timestamp"] = datetime.fromtimestamp(timestamp).isoformat()
                elif ts_format == "lcm":
                    export_data["timestamp"] = int(timestamp * 1_000_000)
                else:
                    export_data["timestamp"] = timestamp

                export_data["channel"] = pkt.channel
                export_data["seqno"] = pkt.seqno
                export_data["size"] = pkt.packet_size

                if decoded_obj and field_paths:
                    # Field extraction mode
                    from lcm_tools.export import FieldExtractor

                    extracted = FieldExtractor.extract_multiple(decoded_obj, field_paths)
                    export_data.update(extracted)
                elif decoded_obj:
                    # Full decode: flatten all fields
                    for attr_name in getattr(decoded_obj, "__slots__", []):
                        try:
                            val = getattr(decoded_obj, attr_name)
                            # Convert bytes to hex for JSON/CSV safety
                            if isinstance(val, bytes):
                                val = val.hex()
                            export_data[attr_name] = val
                        except AttributeError:
                            pass
                else:
                    # No decode: export metadata only
                    export_data["payload_hex"] = pkt.payload.hex()

                # Write to exporters
                if csv_writer:
                    csv_writer.write_row(export_data)
                if jsonl_writer:
                    jsonl_writer.write_row(export_data)

                # Progress every 100 messages
                if received % 100 == 0:
                    print(f"Exported {received} messages...", file=sys.stderr)
                continue  # Skip terminal display in export mode

            if raw:
                echo_packet_raw(pkt, received)
            elif decode_cls:
                echo_packet_decoded(pkt, received, decode_cls)
            elif type_registry is not None:
                echo_packet_auto_decode(pkt, received, type_registry)
            else:
                echo_packet_default(pkt, received)

            if count and received >= count:
                break

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        # Close export writers
        if csv_writer:
            csv_writer.close()
        if jsonl_writer:
            jsonl_writer.close()
        _console.print(f"\n[dim]Received {received} message(s).[/dim]")
