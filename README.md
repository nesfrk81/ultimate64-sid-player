# Ultimate64 SID Player

Play SID music files from your Ultimate64/Ultimate-II+ device via the REST API.

## Features

- 🎵 **Play SID files** from USB drive directories
- 🔀 **Shuffle mode** for random playback
- 🔁 **Loop mode** for continuous play
- ⏱️ **Configurable duration** per song
- 🧠 **Memory hack** - automatically reads playlists from C64 memory

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate SID File List (on C64)

Run `sid_finder.prg` on your C64 to scan a directory for SID files:

```bash
# Build the program
python3 build_and_deploy.py sid_finder.bas sid_finder.prg

# Then run it on your C64 (or use Ultimate's file browser)
```

Edit `sid_finder.bas` line 40 to set your SID directory before building.

### 3. Play SID Files

```bash
# Basic usage
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF

# With shuffle and loop
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --random --loop

# Set duration per song
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --duration 120
```

## How It Works

See [README_SID_PLAYER.md](README_SID_PLAYER.md) for detailed documentation.

## Requirements

- Ultimate64 or Ultimate-II+ (firmware 3.11+)
- Python 3.6+
- USB drive with SID files
- **Software IEC** enabled on Ultimate

## Configuration

Default Ultimate IP: `192.168.1.234`

Override with `--host`:
```bash
python3 play_all_sids.py /USB0/MUSIC --host 192.168.1.100
```

## Files

| File | Description |
|------|-------------|
| `play_all_sids.py` | Main Python player script |
| `sid_finder.bas` | C64 BASIC source - scans for SID files |
| `sid_finder.prg` | Compiled PRG for C64 |
| `memload.bas` | Memory loader source (used automatically) |
| `memload.prg` | Compiled memory loader |
| `build_and_deploy.py` | BASIC tokenizer/compiler |
| `basic_tokenizer.py` | Tokenizer library |

## License

MIT
