#!/usr/bin/env python3
"""
Ultimate SID Player - Play SID files from your Ultimate64/Ultimate-II+

This script reads a SIDFILES.TXT file from the Ultimate device and plays
all SID files listed in it.

Features:
- Reads SID file list from SIDFILES.TXT via C64 memory
- Random/shuffle mode with --random flag
- Loop mode with --loop flag
- Configurable duration per song
- Keyboard controls: SPACE = next song, Q = quit and reset C64
"""

import sys
import os
import time
import random
import argparse
import requests
import select
import termios
import tty
import json

# Path to script directory and config file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "usidp_config.json")

# Default configuration
DEFAULT_CONFIG = {
    "host": "192.168.1.234",
    "port": 80,
    "base_path": "/USB0/MUSIC/HVSC/BESTOF",
    "duration": 180,
    "random": False,
    "loop": False
}

# Ultimate device configuration (will be set from config file or CLI args)
ULTIMATE_HOST = DEFAULT_CONFIG["host"]
ULTIMATE_PORT = DEFAULT_CONFIG["port"]
ULTIMATE_BASE_URL = f"http://{ULTIMATE_HOST}:{ULTIMATE_PORT}"
API_BASE = f"{ULTIMATE_BASE_URL}/v1"

# Default song duration in seconds (used when duration can't be determined)
DEFAULT_SONG_DURATION = DEFAULT_CONFIG["duration"]


def load_config():
    """Load configuration from usidp_config.json, creating it if it doesn't exist."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            # Merge with defaults for any missing keys
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")
            return DEFAULT_CONFIG.copy()
    else:
        # Create default config file
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save configuration to usidp_config.json."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Warning: Could not save config file: {e}")


def get_device_for_path(path):
    """
    Determine the IEC device number based on the path.
    USB0 = device 11, USB1 = device 10
    """
    path_upper = path.upper()
    if path_upper.startswith("/USB1") or path_upper.startswith("USB1"):
        return 10
    # Default to USB0 (device 11)
    return 11


def get_key_press():
    """
    Check for a key press without blocking.
    Returns the key pressed, or None if no key was pressed.
    """
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None


class RawTerminal:
    """Context manager for raw terminal mode (non-blocking key input)."""
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = None
    
    def __enter__(self):
        try:
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
            # Set non-blocking
            import fcntl
            self.old_flags = fcntl.fcntl(self.fd, fcntl.F_GETFL)
            fcntl.fcntl(self.fd, fcntl.F_SETFL, self.old_flags | os.O_NONBLOCK)
        except:
            pass
        return self
    
    def __exit__(self, *args):
        if self.old_settings:
            try:
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
                import fcntl
                fcntl.fcntl(self.fd, fcntl.F_SETFL, self.old_flags)
            except:
                pass


def read_file_via_memory(base_path, filename="SIDFILES.TXT", verbose=True):
    """
    Read a file from the Ultimate by loading it into C64 memory via a BASIC program,
    then reading the memory via the REST API.
    
    Steps:
    1. Generate a loader program that loads the specific file to C64 memory
    2. Run the PRG on the C64
    3. Wait for it to complete
    4. Read memory at $C000 
    5. Return the file contents
    """
    if verbose:
        print(f"  Reading SIDFILES.TXT from C64 memory...")
    
    # Determine the correct device number based on path (USB0=11, USB1=10)
    device = get_device_for_path(base_path)
    
    # Build the BASIC program dynamically for the target path
    bas_content = f'''10 REM Load file to memory via CD
20 PRINT CHR$(147);"LOADING FILE TO MEMORY"
30 PRINT
40 REM First change directory (device {device})
50 OPEN 15,{device},15,"CD:/{base_path.lstrip('/')}"
60 CLOSE 15
70 PRINT "CD DONE"
80 REM Small delay for drive
90 FOR I=1 TO 500:NEXT I
100 REM Open file in current directory  
110 OPEN 1,{device},0,"{filename},S,R"
120 IF ST<>0 THEN PRINT "OPEN ERR ST=";ST:GOTO 250
130 PRINT "FILE OPENED"
140 REM Read to $C000
150 A=49152
160 N=0
170 GET#1,C$
180 IF ST=64 THEN GOTO 210
190 IF LEN(C$)>0 THEN POKE A,ASC(C$):A=A+1:N=N+1:GOTO 170
200 POKE A,0:A=A+1:N=N+1:GOTO 170
210 POKE A,0
220 CLOSE 1
230 PRINT "LOADED ";N;" BYTES"
240 POKE 49150,N-256*INT(N/256):POKE 49151,INT(N/256)
250 END
'''
    
    # Write temporary .bas file
    import tempfile
    import subprocess
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bas', delete=False) as f:
        f.write(bas_content)
        bas_file = f.name
    
    prg_file = bas_file.replace('.bas', '.prg')
    
    try:
        # Tokenize the BASIC file using our tokenizer
        tokenizer_path = os.path.join(SCRIPT_DIR, "build_and_deploy.py")
        result = subprocess.run(
            ['python3', tokenizer_path, bas_file, prg_file],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0 or not os.path.exists(prg_file):
            if verbose:
                print(f"    ✗ Failed to tokenize BASIC program")
            return None
        
        # Read the PRG file
        with open(prg_file, 'rb') as f:
            prg_data = f.read()
        
        import base64
        prg_base64 = base64.b64encode(prg_data).decode('ascii')
        
        # Reset the machine first
        reset_url = f"{API_BASE}/machine:reset"
        try:
            requests.put(reset_url, timeout=5)
            time.sleep(2)  # Wait for reset
        except:
            pass
        
        # Run the PRG via the API
        run_url = f"{API_BASE}/runners:run_prg"
        response = requests.post(run_url, data=prg_data, 
                                headers={'Content-Type': 'application/octet-stream'},
                                timeout=10)
        
        if response.status_code not in (200, 204):
            if verbose:
                print(f"    ✗ Failed to run PRG: HTTP {response.status_code}")
            return None
        
        if verbose:
            print(f"    Loading file to C64 memory...")
        
        # Wait for the program to complete (file I/O takes time)
        time.sleep(8)
        
        # Read memory at $C000 (where the file content is stored)
        # The API returns raw bytes, not JSON
        content_bytes = b''
        
        for offset in range(0, 2048, 256):
            addr = 0xC000 + offset
            mem_url = f"{API_BASE}/machine:readmem?address={addr:04x}&length=256"
            response = requests.get(mem_url, timeout=10)
            
            if response.status_code != 200:
                if verbose and offset == 0:
                    print(f"    ✗ Failed to read memory: HTTP {response.status_code}")
                break
            
            # Check if response is raw bytes or JSON
            try:
                data = response.json()
                if 'data' in data:
                    chunk = bytes.fromhex(data['data'])
                else:
                    chunk = response.content
            except:
                chunk = response.content
            
            # Find null terminator
            null_pos = chunk.find(b'\x00')
            if null_pos >= 0:
                content_bytes += chunk[:null_pos]
                break
            content_bytes += chunk
        
        if not content_bytes:
            if verbose:
                print(f"    ✗ No data in memory")
            return None
        
        # Decode as Latin-1 (PETSCII compatible)
        # Replace CR (0x0D) with newlines
        content = content_bytes.decode('latin-1').replace('\r', '\n')
        
        if verbose:
            print(f"    ✓ Read {len(content_bytes)} bytes from C64 memory")
        
        return content
        
    except Exception as e:
        if verbose:
            print(f"    ✗ Error: {e}")
        return None
    finally:
        # Cleanup temp files
        try:
            os.unlink(bas_file)
        except:
            pass
        try:
            os.unlink(prg_file)
        except:
            pass


def get_file_info(file_path):
    """
    Get file information from the Ultimate device.
    """
    url = f"{API_BASE}/files/{file_path.lstrip('/')}:info"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        return None


def get_sid_info(file_path):
    """
    Try to get SID file information including duration.
    Returns dict with 'duration' (in seconds) and other info if available.
    """
    info = {
        'duration': DEFAULT_SONG_DURATION,
        'title': None,
        'author': None,
        'songs': 1
    }
    
    # Try to get file info from Ultimate API
    file_info = get_file_info(file_path)
    if file_info:
        # Check if API returns duration info
        if 'duration' in file_info:
            info['duration'] = file_info['duration']
        if 'length' in file_info:
            info['duration'] = file_info['length']
        if 'playtime' in file_info:
            info['duration'] = file_info['playtime']
        if 'title' in file_info:
            info['title'] = file_info['title']
        if 'author' in file_info:
            info['author'] = file_info['author']
        if 'songs' in file_info:
            info['songs'] = file_info['songs']
    
    return info


def play_sid_file(file_path, song_number=1):
    """
    Play a SID file using the Ultimate REST API.
    Returns True if successful.
    """
    url = f"{API_BASE}/runners:sidplay"
    params = {"file": file_path}
    if song_number:
        params["songnr"] = song_number
    
    try:
        response = requests.put(url, params=params, timeout=10)
        if response.status_code in (200, 204):
            return True
        else:
            print(f"✗ Failed to play {file_path}: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error playing {file_path}: {e}")
        return False


def stop_sid():
    """
    Stop the currently playing SID.
    """
    url = f"{API_BASE}/runners:sidplay"
    try:
        response = requests.delete(url, timeout=5)
        return response.status_code in (200, 204)
    except:
        return False


def reset_machine():
    """
    Reset the C64 machine.
    """
    url = f"{API_BASE}/machine:reset"
    try:
        response = requests.put(url, timeout=5)
        return response.status_code in (200, 204)
    except:
        return False


def parse_sidfiles_txt(content, base_path):
    """
    Parse the SIDFILES.TXT content and return list of full paths.
    """
    sid_files = []
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        # Skip empty lines, headers, and metadata
        if not line:
            continue
        if line.startswith('===') or line.startswith('PATH:') or line.startswith('TOTAL:'):
            continue
        # Check if it looks like a SID filename
        if line.upper().endswith('.SID'):
            # Build full path
            full_path = f"{base_path}/{line}"
            sid_files.append(full_path)
    
    return sid_files


def format_duration(seconds):
    """Format duration as MM:SS"""
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins}:{secs:02d}"


def play_all_sids(sid_list_path, base_path, duration=None, song_number=1, 
                  shuffle=False, loop=False, local_list=None):
    """
    Play all SID files from the list file.
    
    Args:
        sid_list_path: Path to SIDFILES.TXT on Ultimate
        base_path: Base directory path for SID files
        duration: Duration per song (None = auto-detect or default)
        song_number: Song number to play from each SID
        shuffle: Randomize play order
        loop: Loop playlist forever
        local_list: Path to local file with SID list (bypasses Ultimate file reading)
    """
    print("=" * 60)
    device_num = get_device_for_path(base_path)
    print("Ultimate SID Player")
    print("=" * 60)
    print(f"Host: {ULTIMATE_BASE_URL}")
    print(f"Base path: {base_path}")
    print(f"IEC Device: {device_num} ({'USB0' if device_num == 11 else 'USB1'})")
    print("-" * 60)
    
    content = None
    
    # Option 1: Use local file if provided
    if local_list:
        print(f"Reading local SID list: {local_list}")
        try:
            with open(local_list, 'r', encoding='latin-1') as f:
                content = f.read()
            print(f"  ✓ Loaded from local file")
        except Exception as e:
            print(f"  ✗ Error reading local file: {e}")
            return
    else:
        # Read from Ultimate device via C64 memory
        print(f"Reading SID file list from Ultimate...")
        
        # Try different filename variants (C64 sequential files have .SEQ extension)
        for fname in ["SIDFILES.TXT", "SIDFILES.TXT.SEQ", "sidfiles.txt.seq"]:
            content = read_file_via_memory(base_path, fname, verbose=True)
            if content:
                print(f"  ✓ Read SIDFILES.TXT successfully")
                break
        
        if not content:
            print(f"\n✗ Failed to read SID file list from Ultimate")
            print("\nAlternatives:")
            print("  1. Copy sidfiles.txt.seq to your computer and use --local-list:")
            print(f"     python3 play_all_sids.py {base_path} --local-list sidfiles.txt.seq")
            print("  2. Make sure SIDFILES.TXT exists on the Ultimate device")
            print("     (Run sid_finder.prg on the C64 first)")
            return
    
    # Parse the file list
    sid_files = parse_sidfiles_txt(content, base_path)
    
    if not sid_files:
        print("No SID files found in the list!")
        return
    
    print(f"Found {len(sid_files)} SID file(s)")
    print("-" * 60)
    
    # Shuffle if requested
    if shuffle:
        random.shuffle(sid_files)
        print("🔀 Shuffle mode enabled")
    
    if loop:
        print("🔁 Loop mode enabled")
    
    print()
    print("Controls: [SPACE] = next song, [Q] = quit and reset C64")
    print("-" * 60)
    
    quit_requested = False
    
    try:
        with RawTerminal():
            while True:  # For loop mode
                playlist = sid_files.copy()
                if shuffle:
                    random.shuffle(playlist)
                
                for i, sid_file in enumerate(playlist, 1):
                    if quit_requested:
                        break
                    
                    filename = sid_file.split('/')[-1]
                    
                    # Get SID info for duration
                    if duration is None:
                        sid_info = get_sid_info(sid_file)
                        song_duration = sid_info['duration']
                    else:
                        song_duration = duration
                    
                    # Use \r\n for raw terminal mode
                    sys.stdout.write(f"\r\n[{i}/{len(playlist)}] {filename}\r\n")
                    sys.stdout.write(f"    Path: {sid_file}\r\n")
                    sys.stdout.write(f"    Duration: {format_duration(song_duration)}\r\n")
                    sys.stdout.flush()
                    
                    if play_sid_file(sid_file, song_number):
                        sys.stdout.write(f"    ▶ Playing...\r\n")
                        sys.stdout.flush()
                        
                        # Wait for song duration with countdown, check for key presses
                        remaining = song_duration
                        skip_song = False
                        
                        while remaining > 0 and not skip_song and not quit_requested:
                            mins = int(remaining) // 60
                            secs = int(remaining) % 60
                            sys.stdout.write(f"\r    ⏱ Remaining: {mins}:{secs:02d}  [SPACE=skip, Q=quit]  ")
                            sys.stdout.flush()
                            
                            # Check for key press
                            key = get_key_press()
                            if key:
                                if key == ' ':
                                    skip_song = True
                                    sys.stdout.write(f"\r    ⏭ Skipping...                              \r\n")
                                    sys.stdout.flush()
                                elif key.lower() == 'q':
                                    quit_requested = True
                                    sys.stdout.write(f"\r    ⏹ Quit requested...                        \r\n")
                                    sys.stdout.flush()
                            
                            time.sleep(0.1)  # Check more frequently for key presses
                            remaining -= 0.1
                        
                        if not skip_song and not quit_requested:
                            sys.stdout.write(f"\r    ✓ Finished                                  \r\n")
                            sys.stdout.flush()
                    else:
                        sys.stdout.write("    ✗ Skipping...\r\n")
                        sys.stdout.flush()
                        time.sleep(2)
                
                if quit_requested or not loop:
                    break
                
                sys.stdout.write("\r\n" + "=" * 60 + "\r\n")
                sys.stdout.write("🔁 Restarting playlist...\r\n")
                sys.stdout.write("=" * 60 + "\r\n")
                sys.stdout.flush()
    
    except KeyboardInterrupt:
        sys.stdout.write("\r\n\r\n⏹ Playback interrupted by user\r\n")
        sys.stdout.flush()
    
    # Clean up
    if quit_requested:
        print("\nResetting C64...")
        reset_machine()
    stop_sid()
    
    print("\n" + "=" * 60)
    print("Finished!")


def main():
    global ULTIMATE_BASE_URL, API_BASE, ULTIMATE_HOST, ULTIMATE_PORT, DEFAULT_SONG_DURATION
    
    # Load config file
    config = load_config()
    
    parser = argparse.ArgumentParser(
        description='Play SID files from SIDFILES.TXT on Ultimate64',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  %(prog)s                                    # Use config defaults
  %(prog)s /USB0/MUSIC/HVSC/BESTOF            # Specify path
  %(prog)s --random --loop                    # Shuffle and loop
  %(prog)s --duration 120                     # 2 minutes per song

Config file: {CONFIG_FILE}
  Edit this file to set default host, port, base_path, duration, etc.

Device mapping: USB0 = device 11, USB1 = device 10

Note: Run sid_finder.prg on the C64 first to generate SIDFILES.TXT
        """
    )
    
    parser.add_argument('path', nargs='?',
                        help=f'Base path to SID files (default from config: {config["base_path"]})',
                        default=None)
    
    parser.add_argument('--list-file', '-l',
                        help='Path to SIDFILES.TXT on Ultimate (default: <path>/SIDFILES.TXT)',
                        default=None)
    
    parser.add_argument('--local-list', '-L',
                        help='Use a local file for the SID list instead of reading from Ultimate',
                        default=None)
    
    parser.add_argument('--duration', '-d',
                        type=int,
                        help=f'Duration per song in seconds (default from config: {config["duration"]})',
                        default=None)
    
    parser.add_argument('--song', '-s',
                        type=int,
                        help='Song number to play from each SID (default: 1)',
                        default=1)
    
    parser.add_argument('--random', '-r',
                        action='store_true',
                        default=None,
                        help=f'Shuffle/randomize play order (default from config: {config["random"]})')
    
    parser.add_argument('--loop',
                        action='store_true',
                        default=None,
                        help=f'Loop playlist forever (default from config: {config["loop"]})')
    
    parser.add_argument('--host',
                        help=f'Ultimate device hostname/IP (default from config: {config["host"]})',
                        default=None)
    
    parser.add_argument('--port',
                        type=int,
                        help=f'Ultimate device port (default from config: {config["port"]})',
                        default=None)
    
    args = parser.parse_args()
    
    # Apply config values, CLI args override config
    host = args.host if args.host else config["host"]
    port = args.port if args.port else config["port"]
    base_path = args.path.rstrip('/') if args.path else config["base_path"].rstrip('/')
    duration = args.duration if args.duration is not None else config["duration"]
    shuffle = args.random if args.random is not None else config["random"]
    loop = args.loop if args.loop is not None else config["loop"]
    
    # Update globals
    ULTIMATE_HOST = host
    ULTIMATE_PORT = port
    ULTIMATE_BASE_URL = f"http://{host}:{port}"
    API_BASE = f"{ULTIMATE_BASE_URL}/v1"
    DEFAULT_SONG_DURATION = duration
    
    # Determine list file path
    if args.list_file:
        list_file = args.list_file
    else:
        list_file = f"{base_path}/SIDFILES.TXT"
    
    play_all_sids(
        sid_list_path=list_file,
        base_path=base_path,
        duration=duration,
        song_number=args.song,
        shuffle=shuffle,
        loop=loop,
        local_list=args.local_list
    )


if __name__ == "__main__":
    main()
