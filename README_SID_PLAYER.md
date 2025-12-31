# Ultimate SID Player

A Python-based SID music player for the **Ultimate64**, **Ultimate-II+**, and **Ultimate-II+L** that reads playlist files directly from the device and plays them via the REST API.

## Overview

This system consists of two parts:

1. **C64 Side**: A BASIC program (`sid_finder.prg`) that scans a directory for `.SID` files and writes them to `SIDFILES.TXT`
2. **PC Side**: A Python script (`play_all_sids.py`) that reads the playlist and plays the SID files

```
┌─────────────────────────────────────────────────────────────────┐
│                        WORKFLOW                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [1] Run sid_finder.prg on C64                                  │
│       │  (prompts for path or uses current directory)           │
│       ▼                                                          │
│  [2] SIDFILES.TXT created on USB drive                          │
│       │                                                          │
│       ▼                                                          │
│  [3] Run play_all_sids.py on PC                                 │
│       │                                                          │
│       ▼                                                          │
│  [4] Auto-uploads loader, reads SIDFILES.TXT via C64 memory     │
│       │                                                          │
│       ▼                                                          │
│  [5] Plays SID files via REST API                               │
│       │                                                          │
│       └── [SPACE] = skip song, [Q] = quit & reset C64           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Requirements

### Hardware
- **Ultimate64**, **Ultimate-II+**, or **Ultimate-II+L** with firmware 3.11+
- USB drive with SID files (e.g., HVSC collection)

### Software
- Python 3.6+
- `requests` library: `pip install requests`

### Ultimate Configuration
- **Software IEC** must be enabled in the Ultimate menu
- USB drive accessible as device 11 (USB0) or device 10 (USB1)

## Step 1: Generate the SID File List (C64)

Run `sid_finder.prg` on your C64 to scan a directory and create `SIDFILES.TXT`.

### Build the Program

```bash
python3 build_and_deploy.py sid_finder.bas sid_finder.prg
```

### Run on C64

The program will prompt you for the path:

```
SID FILE FINDER
===============

ENTER PATH TO SID FILES
(WITHOUT LEADING /)
EXAMPLE: USB0/MUSIC/HVSC/BESTOF
(PRESS ENTER FOR CURRENT DIR)

PATH: _
```

- Enter a path like `USB0/MUSIC/HVSC/BESTOF`
- Or press **ENTER** to scan the current directory
- Leading `/` is automatically stripped if included

The program will:
1. Change to the specified directory (if provided)
2. Wait for you to press a key when drive LED stops
3. Scan for `.SID` files
4. Write them to `SIDFILES.TXT` in that directory

## Step 2: Play the SID Files (PC)

### Basic Usage

```bash
# Use defaults from config file
python3 play_all_sids.py

# Or specify a path
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF
```

### Keyboard Controls During Playback

| Key | Action |
|-----|--------|
| **SPACE** | Skip to next song |
| **Q** | Quit and reset C64 |

### Command Line Options

```bash
# Shuffle/random order
python3 play_all_sids.py --random

# Loop forever
python3 play_all_sids.py --loop

# Set duration per song (seconds)
python3 play_all_sids.py --duration 120

# Combine options
python3 play_all_sids.py --random --loop --duration 180

# Custom Ultimate device address
python3 play_all_sids.py --host 192.168.1.100
```

### All Options

| Option | Short | Description |
|--------|-------|-------------|
| `path` | | Base path to SID files (default from config) |
| `--random` | `-r` | Shuffle/randomize play order |
| `--loop` | | Loop playlist forever |
| `--duration N` | `-d N` | Duration per song in seconds |
| `--song N` | `-s N` | Song number to play from multi-song SIDs |
| `--local-list FILE` | `-L FILE` | Use a local playlist file |
| `--host IP` | | Ultimate device IP |
| `--port N` | | Ultimate device port |

## Configuration File

Settings are stored in `usidp_config.json`:

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

Edit this file to set your defaults. Command line arguments override config values.

## Device Auto-Detection

The IEC device number is automatically determined from the path:
- **USB0** → device 11
- **USB1** → device 10

## How It Works

The Ultimate REST API doesn't support reading file contents directly. To work around this, `play_all_sids.py` automatically:

1. **Generates a BASIC loader** for the target directory
2. **Uploads and runs** it on the C64 via `POST /v1/runners:run_prg`
3. **Waits** for the C64 to load `SIDFILES.TXT` into memory at `$C000`
4. **Reads memory** via `GET /v1/machine:readmem`
5. **Parses** the playlist and plays SID files via `PUT /v1/runners:sidplay`

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/runners:run_prg` | POST | Upload and run PRG file |
| `/v1/runners:sidplay` | PUT | Play a SID file |
| `/v1/machine:readmem` | GET | Read C64 memory |
| `/v1/machine:reset` | PUT | Reset the C64 |
| `/v1/files/{path}:info` | GET | Get file information |

Reference: [Ultimate REST API Documentation](https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html)

## File Structure

```
c64/
├── play_all_sids.py      # Main Python player script
├── sid_finder.bas        # C64 BASIC source - scans for SID files
├── sid_finder.prg        # Compiled PRG for C64
├── memload.bas           # Memory loader source (used automatically)
├── memload.prg           # Compiled memory loader
├── usidp_config.json     # Configuration file
├── build_and_deploy.py   # BASIC tokenizer
└── basic_tokenizer.py    # Tokenizer library
```

## Troubleshooting

### "Device not present" error on C64
- Enable **Software IEC** in Ultimate menu
- Check device number (USB0=11, USB1=10)

### No data read from C64 memory
- Make sure `SIDFILES.TXT` exists (run `sid_finder.prg` first)
- Try increasing wait time if your drive is slow

### SID files don't play
- Verify the path format: `/USB0/MUSIC/HVSC/BESTOF/filename.SID`
- Check Ultimate is reachable: `curl http://YOUR_IP/v1/version`

### Using local playlist file
If reading from C64 doesn't work, copy `SIDFILES.TXT.SEQ` from your USB drive and use:
```bash
python3 play_all_sids.py --local-list sidfiles.txt.seq
```

## Example Output

```
============================================================
Ultimate SID Player
============================================================
Host: http://192.168.1.234:80
Base path: /USB0/MUSIC/HVSC/BESTOF
IEC Device: 11 (USB0)
------------------------------------------------------------
Reading SID file list from Ultimate...
  Reading SIDFILES.TXT from C64 memory...
    Loading file to C64 memory...
    ✓ Read 119 bytes from C64 memory
  ✓ Read SIDFILES.TXT successfully
Found 3 SID file(s)
------------------------------------------------------------
Controls: [SPACE] = next song, [Q] = quit and reset C64
------------------------------------------------------------
🔀 Shuffle mode enabled
🔁 Loop mode enabled

[1/3] COMMANDO.SID
    Path: /USB0/MUSIC/HVSC/BESTOF/COMMANDO.SID
    Duration: 3:00
    ▶ Playing...
    ⏱ Remaining: 2:45  [SPACE=skip, Q=quit]
```

## Compatible Devices

- ✅ Ultimate64
- ✅ Ultimate-II+
- ✅ Ultimate-II+L

## License

This project is provided as-is for the Commodore 64 and Ultimate community.
