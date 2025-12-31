# Ultimate64 SID Player

A Python-based SID music player that reads playlist files directly from your Ultimate64/Ultimate-II+ device and plays them via the REST API.

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
│       │                                                          │
│       ▼                                                          │
│  [2] SIDFILES.TXT created on USB drive                          │
│       │                                                          │
│       ▼                                                          │
│  [3] Run play_all_sids.py on PC ─────────────────┐              │
│       │                                           │              │
│       │  (API file read fails)                    │              │
│       ▼                                           │              │
│  [4] Memory Hack: Auto-uploads memload.prg ◄─────┘              │
│       │                                                          │
│       ▼                                                          │
│  [5] Reads SIDFILES.TXT via C64 memory ($C000)                  │
│       │                                                          │
│       ▼                                                          │
│  [6] Plays SID files via REST API                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Requirements

### Hardware
- Ultimate64 or Ultimate-II+ with firmware 3.11+
- USB drive with SID files (e.g., HVSC collection)

### Software
- Python 3.6+
- `requests` library: `pip install requests`

### Ultimate64 Configuration
- **Software IEC** must be enabled
- USB drive should be accessible as device 11 (USB0) or device 10 (USB1)

## Step 1: Generate the SID File List (C64)

First, you need to run `sid_finder.prg` on your C64 to scan a directory and create `SIDFILES.TXT`.

### Build the Program

```bash
python3 build_and_deploy.py sid_finder.bas sid_finder.prg
```

### Edit the Directory Path

Before building, edit `sid_finder.bas` line 40 to set your SID directory:

```basic
40 DIR$="USB0/MUSIC/HVSC/BESTOF"
```

### Run on C64

Either:
- Copy `sid_finder.prg` to your USB drive and load it manually
- Or use the MCP tools to run it directly:

```bash
# Via MCP tool
mcp_ultimate64-mcp_ultimate_run_prg_binary --file_path sid_finder.prg
```

The program will:
1. Change to the specified directory
2. Read the directory listing
3. Find all `.SID` files
4. Write them to `SIDFILES.TXT` in the same directory

**Output on C64 screen:**
```
CHANGING TO DIRECTORY: /USB0/MUSIC/HVSC/BESTOF
DIRECTORY CHANGED. OPENING FOR READ...
OPENING SIDFILES.TXT FOR WRITE...
1. COMIC_BAKERY.SID
2. COMMANDO.SID
3. CYBERNOID_II.SID
TOTAL SID FILES FOUND: 3
```

## Step 2: Play the SID Files (PC)

### Basic Usage

```bash
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF
```

### With Options

```bash
# Shuffle/random order
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --random

# Set duration per song (seconds)
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --duration 120

# Loop forever with random order
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --random --loop

# Use a local copy of the playlist
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --local-list sidfiles.txt.seq

# Custom Ultimate device address
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --host 192.168.1.100
```

### All Options

| Option | Short | Description |
|--------|-------|-------------|
| `--random` | `-r` | Shuffle/randomize play order |
| `--loop` | | Loop playlist forever |
| `--duration N` | `-d N` | Duration per song in seconds (default: 180) |
| `--song N` | `-s N` | Song number to play from multi-song SIDs |
| `--local-list FILE` | `-L FILE` | Use a local playlist file |
| `--list-file PATH` | `-l PATH` | Path to SIDFILES.TXT on Ultimate |
| `--host IP` | | Ultimate device IP (default: 192.168.1.234) |
| `--port N` | | Ultimate device port (default: 80) |

## How the Memory Hack Works

The Ultimate64 REST API doesn't have an endpoint to read file contents directly. To work around this, `play_all_sids.py` uses a clever "memory hack":

### The Problem

```
GET /v1/files/path/to/file:info  → Returns file metadata (size, type) ✓
GET /v1/files/path/to/file       → Returns 404 or metadata, NOT content ✗
```

### The Solution

1. **Generate a BASIC loader** dynamically for the target file:

```basic
10 REM Load file to memory via CD
20 PRINT CHR$(147);"LOADING FILE TO MEMORY"
50 OPEN 15,11,15,"CD:/USB0/MUSIC/HVSC/BESTOF"
60 CLOSE 15
110 OPEN 1,11,0,"SIDFILES.TXT,S,R"
150 A=49152                          ; $C000
170 GET#1,C$
190 IF LEN(C$)>0 THEN POKE A,ASC(C$):A=A+1:GOTO 170
210 POKE A,0                         ; Null terminator
250 END
```

2. **Tokenize and upload** the BASIC program via the API:

```python
# POST /v1/runners:run_prg
response = requests.post(run_url, data=prg_data, 
                        headers={'Content-Type': 'application/octet-stream'})
```

3. **Wait** for the C64 to load the file into memory (~8 seconds)

4. **Read memory** at $C000 via the API:

```python
# GET /v1/machine:readmem?address=c000&length=256
response = requests.get(mem_url)
content = response.content  # Raw file data!
```

5. **Parse** the playlist and play SID files

### Memory Layout

```
$BFFE-$BFFF: Byte count (low/high byte)
$C000-$CFFF: File content (null-terminated)
```

## API Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/runners:run_prg` | POST | Upload and run PRG file |
| `/v1/machine:readmem` | GET | Read C64 memory |
| `/v1/machine:reset` | PUT | Reset the C64 |
| `/v1/runners:sidplay` | PUT | Play a SID file |
| `/v1/files/{path}:info` | GET | Get file information |

Reference: [Ultimate REST API Documentation](https://1541u-documentation.readthedocs.io/en/latest/api/api_calls.html)

## File Structure

```
c64/
├── sid_finder.bas        # C64 BASIC source - scans for SID files
├── sid_finder.prg        # Compiled PRG for C64
├── memload.bas           # Memory loader source (used by Python script)
├── memload.prg           # Compiled memory loader
├── play_all_sids.py      # Main Python player script
├── build_and_deploy.py   # BASIC tokenizer
└── basic_tokenizer.py    # Tokenizer library
```

## Troubleshooting

### "Device not present" error on C64
- Enable **Software IEC** in Ultimate menu
- Check device number (USB0=11, USB1=10)

### Memory hack fails / no data read
- Increase the wait time in `play_all_sids.py` (line 182: `time.sleep(8)`)
- Make sure `SIDFILES.TXT` exists (run `sid_finder.prg` first)

### SID files don't play
- Verify the path format: `/USB0/MUSIC/HVSC/BESTOF/filename.SID`
- Check Ultimate is reachable: `curl http://192.168.1.234/v1/version`

### Using local playlist file
If the memory hack doesn't work, copy `SIDFILES.TXT.SEQ` from your USB drive to your PC and use:
```bash
python3 play_all_sids.py /USB0/MUSIC/HVSC/BESTOF --local-list sidfiles.txt.seq
```

## Example Output

```
============================================================
Ultimate SID Player
============================================================
Device: http://192.168.1.234:80
Base path: /USB0/MUSIC/HVSC/BESTOF
------------------------------------------------------------
Reading SID file list from Ultimate...
  Trying: /USB0/MUSIC/HVSC/BESTOF/SIDFILES.TXT
  API read failed, trying memory hack...
  Using memory hack to read file...
    Loading file to C64 memory...
    ✓ Read 119 bytes from C64 memory
  ✓ Read via memory hack
Found 3 SID file(s)
------------------------------------------------------------
🔀 Shuffle mode enabled

[1/3] COMMANDO.SID
    Path: /USB0/MUSIC/HVSC/BESTOF/COMMANDO.SID
    Duration: 3:00
    ▶ Playing...
    ⏱ Remaining: 2:45  
```

## License

This project is provided as-is for the Commodore 64 and Ultimate64 community.
