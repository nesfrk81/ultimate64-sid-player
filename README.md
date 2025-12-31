# Ultimate SID Player

Play SID music files from your **Commodore 64 Ultimate**, **Ultimate64**, or **Ultimate-II+** via the REST API.

## Features

- 🎵 **Play SID files** from USB drive directories
- 🔀 **Shuffle mode** for random playback
- 🔁 **Loop mode** for continuous play
- ⏱️ **Configurable duration** per song
- ⌨️ **Keyboard controls**: SPACE = skip, Q = quit
- ⚙️ **Config file** for default settings
- 🔄 **Auto device detection** (USB0=11, USB1=10)

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate SID File List (on C64)

Run `sid_finder.prg` on your C64:

The program will prompt for a path or use the current directory.

### 3. Play SID Files

```bash
# Use defaults from config file
python3 play_all_sids.py

# Or specify path and options
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --random --loop
```

### Keyboard Controls

| Key | Action |
|-----|--------|
| **SPACE** | Skip to next song |
| **Q** | Quit and reset C64 |

## Configuration

Edit `usidp_config.json` to set defaults:

```json
{
    "host": "192.168.1.234",
    "port": 80,
    "base_path": "/USB0/MUSIC/HVSC/BESTOF",
    "duration": 180,
    "random": false,
    "loop": false
}
```

## Documentation

See [README_SID_PLAYER.md](README_SID_PLAYER.md) for detailed documentation.

## Requirements

- **Commodore 64 Ultimate**, **Ultimate64**, or **Ultimate-II+** (firmware 3.11+)
- Python 3.6+
- **Software IEC** enabled on Ultimate

## Files

| File | Description |
|------|-------------|
| `play_all_sids.py` | Main Python player script |
| `sid_finder.bas/prg` | C64 SID scanner |
| `usidp_config.json` | Configuration file |
| `build_and_deploy.py` | BASIC tokenizer |

## License

MIT
