# LCM CLI Tools

**[English](README.md)** | [中文](README_zh.md)

> ROS2-style command line tools for monitoring and debugging LCM (Lightweight Communications and Marshalling) networks.

## Features

```
lcm topic echo <channel>   — View real-time topic data (like ros2 topic echo)
lcm topic list             — List active topics/channels (like ros2 topic list)
lcm topic stats            — Real-time topic stats: rate, bandwidth, msg count (like ros2 topic hz)
lcm topic bw <channel>     — Monitor bandwidth for a single channel with sparkline graph
lcm topic info <channel>   — Detailed channel information with type structure
lcm node list              — List discovered publisher nodes (like ros2 node list)
lcm type list              — List all registered LCM types
lcm type show <type>       — Show type field structure
lcm record                 — Record live LCM traffic to .log file (like ros2 bag record)
lcm play <file.log>        — Replay .log file to multicast (like ros2 bag play)
```

**Highlights**:
- Built-in pure-Python `.lcm` file parser — no `lcm-gen` or `PYTHONPATH` needed
- **Message Export**: CSV/JSONL export with field extraction (`--csv`, `--jsonl`, `--field`)
- **Advanced Monitoring**: Sort/filter stats (`--sort`, `--top`, `--freeze`, `--spark`)
- **Live Watch Mode**: Continuous refresh for topic/node list (`--watch`)
- **Recording & Playback**: Full log file support compatible with `lcm-logger`

## Installation

```bash
# From PyPI
pip install lcm-cli

# From source (development)
git clone https://github.com/Joyserr/lcm-cli.git
cd lcm-cli
pip install -e .

# Optional: traditional lcm-gen Python package decode support
pip install lcm-cli[decode]
```

**Requirements**: Python >= 3.9, `typer`, `rich` (`lcm` package is optional, only for legacy `--type module.Class` decoding).

## Quick Start

```bash
# Show all subcommands
lcm --help

# Show version
lcm --version

# List active channels (listens for 5 seconds)
lcm topic list

# Continuous watch mode (live refresh)
lcm topic list --watch

# View messages on a channel (raw hex format)
lcm topic echo EXAMPLE

# Receive only 10 messages
lcm topic echo EXAMPLE -n 10

# Match multiple channels with regex
lcm topic echo "CAM.*"

# Monitor real-time statistics for all channels
lcm topic stats

# Sort by bandwidth, show top 5
lcm topic stats --sort bw --top 5

# Freeze mode (single snapshot)
lcm topic stats --freeze

# Monitor bandwidth with sparkline graph
lcm topic bw CAMERA --spark

# Detailed channel information
lcm topic info CAMERA --lcm-file types/

# List discovered publisher nodes
lcm node list
```

## Recording & Playback

```bash
# Record all channels to a .log file
lcm record

# Record specific channels with regex
lcm record --channel "CAM.*" -o camera.log

# Record for a fixed duration
lcm record -d 60  # 60 seconds

# Replay a .log file
lcm play camera.log

# Replay at 2x speed
lcm play camera.log --speed 2.0

# Loop playback
lcm play camera.log --loop
```

## Message Export

```bash
# Export to CSV (headers auto-determined from first message)
lcm topic echo EXAMPLE --csv output.csv

# Export to JSON Lines
lcm topic echo EXAMPLE --jsonl output.jsonl

# Extract specific fields
lcm topic echo EXAMPLE --field position --field velocity --csv data.csv

# Extract nested fields
lcm topic echo EXAMPLE --field imu.accel.x --field imu.gyro.y

# Extract array slices
lcm topic echo EXAMPLE --field "position[0:2]"

# Custom timestamp format
lcm topic echo EXAMPLE --csv data.csv --ts-format iso
```

## Advanced Statistics

```bash
# Sort channels by message rate
lcm topic stats --sort rate

# Show top 10 channels by bandwidth
lcm topic stats --sort bw --top 10

# Single snapshot (non-interactive)
lcm topic stats --freeze

# Add sparkline trend visualization
lcm topic stats --spark

# Monitor bandwidth for a single channel
lcm topic bw CAMERA --window 10 --spark

# Read stats from log file
lcm topic stats --from recording.log
```

## Message Decoding

### Type Diagnostics

```bash
# List all registered types
lcm type list

# Filter by package
lcm type list --package exlcm

# Show type structure
lcm type show example_t --lcm-file types/

# Grep search types
lcm type list --grep "sensor"
```

### Method 1: Specify `.lcm` files directly (recommended)

No `lcm-gen` installation, no `PYTHONPATH` configuration. The tool includes a built-in pure-Python parser:

```bash
# Specify a single .lcm file — auto-matches message type by fingerprint
lcm topic echo EXAMPLE --lcm-file types/example_t.lcm

# Specify a directory (recursively scans all .lcm files)
lcm topic echo EXAMPLE -f types/

# Specify multiple paths
lcm topic echo EXAMPLE -f types/ -f extra_types/

# Specify a concrete type name (when .lcm files contain multiple structs)
lcm topic echo EXAMPLE -f types/ --type example_t
```

Supports the complete LCM type system:
- All primitive types (`int8_t` ~ `int64_t`, `float`, `double`, `string`, `boolean`, `byte`)
- Fixed-length and variable-length arrays (`double position[3]`, `int16_t ranges[num_ranges]`)
- Multi-dimensional arrays (`int32_t data[size_a][size_b][size_c]`)
- Nested structs and cross-file type references
- Recursive types (e.g., `node_t children[n]` in a linked-list `node_t`)
- Constant declarations (`const int32_t MAX_SIZE = 100`)

**How it works**: Parses `.lcm` files → builds decode classes in memory (`type()` dynamic creation) → auto-matches by the first 8-byte fingerprint of the payload → decodes and recursively expands nested structs. No files are generated at any point.

### Method 2: Traditional `lcm-gen` generated files

```bash
# Install the lcm Python package
pip install lcm-cli[decode]

# Generate Python files with lcm-gen, then configure PYTHONPATH
lcm-gen --python -d types/ types/example_t.lcm
export PYTHONPATH=types:$PYTHONPATH

# Use --type to specify the decode class (module.Class format)
lcm topic echo EXAMPLE --type exlcm.example_t
```

### Custom Multicast Address

```bash
lcm topic list --lcm-url 239.255.76.68 --lcm-port 7668
```

### Statistics

| Metric | Description |
|--------|-------------|
| Rate (Hz) | Message frequency within a sliding window (last 2000 messages) |
| BW (KB/s) | Bandwidth within the sliding window |
| Avg Size (B) | Average bytes per message |
| Total (KB) | Cumulative total transferred |

## Architecture

```
┌───────────────────────────────────────────────────┐
│                  CLI Layer (Typer)                │
│   topic echo │ topic list │ topic stats │ node    │
├───────────────────────────────────────────────────┤
│              Display Layer (Rich Panel)           │
│   recursive nesting │ hex dump │ stats table      │
├───────────────────────────────────────────────────┤
│           Type Parsing Layer (Pure Python)        │
│   .lcm parse → AST → fingerprint → dynamic class  │
├───────────────────────────────────────────────────┤
│            Protocol Layer (Raw UDP Socket)        │
│       LCM Wire Protocol parsing (zero deps)       │
├───────────────────────────────────────────────────┤
│            UDP Multicast (239.255.76.67)          │
└───────────────────────────────────────────────────┘
```

- **Zero external LCM dependency**: Core functionality directly parses the LCM wire protocol from UDP multicast packets
- **Built-in type parsing**: Pure-Python `.lcm` file parser + runtime decode class generator
- **Node discovery**: Infers different publishers from UDP packet source IP:port
- **Legacy decode compatible**: Optional `lcm` Python package for `--type module.Class` decoding

## LCM Protocol

LCM uses UDP multicast for communication (default `239.255.76.67:7667`).

**Short messages** (< 64KB): 8-byte header (magic=0x4c433032 + seqno) + channel name (null-terminated) + payload

**Fragmented messages**: 20-byte header (magic=0x4c433033 + seqno + payload_size + fragment_offset + fragment_no + n_fragments)

Reference: [LCM UDP Multicast Protocol](https://lcm-proj.github.io/lcm/content/udp-multicast-protocol.html)

## LCM vs ROS2 Concepts

| LCM Concept | ROS2 Equivalent | Description |
|-------------|----------------|-------------|
| Channel | Topic | Message publish/subscribe conduit |
| UDP (IP:port) | Node | LCM has no native node concept; inferred from publisher address |
| Fingerprint | Message Type Hash | Unique identifier for a message type |

## Project Structure

```
src/lcm_cli/
├── __init__.py                  # Package definition + version
├── __main__.py                  # python -m lcm_cli entry point
├── cli.py                       # Typer entry point, registers subcommands
├── commands/
│   ├── topic_echo.py            # lcm topic echo (with --csv/--jsonl export)
│   ├── topic_list.py            # lcm topic list (with --watch mode)
│   ├── topic_stats.py           # lcm topic stats (with --sort/--top/--freeze)
│   ├── topic_bw.py              # lcm topic bw (bandwidth monitor)
│   ├── topic_info.py            # lcm topic info (channel details)
│   ├── node_list.py             # lcm node list (with --watch mode)
│   ├── type_list.py             # lcm type list
│   ├── type_show.py             # lcm type show
│   ├── record.py                # lcm record
│   └── play.py                  # lcm play
├── core/
│   ├── discovery.py             # Passive channel/node discovery
│   ├── stats.py                 # Real-time statistics (rate, bandwidth)
│   ├── lcm_type_parser.py       # .lcm file parser + fingerprint algorithm
│   └── lcm_type_builder.py      # Runtime decode class generation + TypeRegistry
├── display/
│   ├── echo_display.py          # Rich panel display (with recursive nesting)
│   ├── stats_display.py         # Statistics table display (with sparkline)
│   └── type_display.py          # Type structure table display
├── export.py                    # Field extraction + CSV/JSONL writers
├── lcm_log.py                   # LCM log file reader/writer (lcm-logger compatible)
├── listener.py                  # UDP multicast listener thread
├── protocol.py                  # LCM Wire Protocol parser
└── source.py                    # PacketSource abstraction (live/offline)
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Network Configuration

If you can't receive messages, check your multicast routing:

**macOS:**
```bash
# View multicast routes
netstat -rn | grep 239

# Add route if needed
sudo route add -net 239.255.76.0/24 -interface en0
```

**Linux:**
```bash
# Add route
sudo ip route add 239.255.76.0/24 dev eth0
```

## License

MIT
