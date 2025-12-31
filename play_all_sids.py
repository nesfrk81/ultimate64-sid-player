#!/usr/bin/env python3
"""
Play all SID files from a list file on the Commodore 64 Ultimate

This script reads a SIDFILES.TXT file from the Ultimate device and plays
all SID files listed in it.

Features:
- Reads SID file list from SIDFILES.TXT on the Ultimate
- Random/shuffle mode with --random flag
- Configurable delay between songs
- Attempts to get SID duration from file info
"""

import sys
import os
import time
import random
import argparse
import requests
import struct

# Ultimate device configuration
ULTIMATE_HOST = "192.168.1.234"
ULTIMATE_PORT = 80
ULTIMATE_BASE_URL = f"http://{ULTIMATE_HOST}:{ULTIMATE_PORT}"
API_BASE = f"{ULTIMATE_BASE_URL}/v1"

# Default song duration in seconds (used when duration can't be determined)
DEFAULT_SONG_DURATION = 180  # 3 minutes

# Path to the memory loader PRG (for reading files via C64 memory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMLOAD_PRG = os.path.join(SCRIPT_DIR, "memload.prg")


def read_file_from_ultimate(file_path, verbose=True):
    """
    Read a text file from the Ultimate device using the REST API.
    Tries multiple API endpoints and URL formats.
    """
    path = file_path.lstrip('/')
    
    # Try different URL formats
    urls_to_try = [
        f"{API_BASE}/files/{path}",
        f"{API_BASE}/files/{path}:read",
        f"{API_BASE}/files:read?path=/{path}",
        f"{ULTIMATE_BASE_URL}/files/{path}",
    ]
    
    headers_to_try = [
        {},
        {"Accept": "text/plain"},
        {"Accept": "application/octet-stream"},
    ]
    
    for url in urls_to_try:
        for headers in headers_to_try:
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    # Check if we got actual content (not JSON error)
                    content = response.text
                    if content and not content.strip().startswith('{'):
                        return content
                    # If JSON, might be file info not content
                    try:
                        data = response.json()
                        if 'content' in data:
                            return data['content']
                        if 'data' in data:
                            return data['data']
                    except:
                        return content
            except Exception as e:
                pass
    
    if verbose:
        print(f"    Could not read file via API")
    return None


def read_file_via_memory(base_path, filename="SIDFILES.TXT", verbose=True):
    """
    Read a file from the Ultimate by loading it into C64 memory via a BASIC program,
    then reading the memory via the REST API.
    
    This is a workaround since the Ultimate API doesn't support reading file contents directly.
    
    Steps:
    1. Generate a custom memload.prg that loads the specific file
    2. Run the PRG on the C64
    3. Wait for it to complete
    4. Read memory at $C000 
    5. Return the file contents
    """
    if verbose:
        print(f"  Using memory hack to read file...")
    
    # Build the BASIC program dynamically for the target path
    bas_content = f'''10 REM Load file to memory via CD
20 PRINT CHR$(147);"LOADING FILE TO MEMORY"
30 PRINT
40 REM First change directory
50 OPEN 15,11,15,"CD:/{base_path.lstrip('/')}"
60 CLOSE 15
70 PRINT "CD DONE"
80 REM Small delay for drive
90 FOR I=1 TO 500:NEXT I
100 REM Open file in current directory  
110 OPEN 1,11,0,"{filename},S,R"
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
    print("Ultimate SID Player")
    print("=" * 60)
    print(f"Device: {ULTIMATE_BASE_URL}")
    print(f"Base path: {base_path}")
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
        # Option 2: Read from Ultimate device
        print(f"Reading SID file list from Ultimate...")
        
        # Try different filename variants (C64 sequential files have .SEQ extension)
        variants = [
            sid_list_path,
            sid_list_path + ".SEQ",
            sid_list_path + ".seq",
            sid_list_path.replace(".TXT", ".TXT.SEQ"),
            sid_list_path.replace(".txt", ".txt.seq"),
            # Also try lowercase
            sid_list_path.lower(),
            sid_list_path.lower() + ".seq",
        ]
        # Remove duplicates while preserving order
        variants = list(dict.fromkeys(variants))
        
        for variant in variants:
            print(f"  Trying: {variant}")
            content = read_file_from_ultimate(variant, verbose=False)
            if content:
                print(f"  ✓ Found: {variant}")
                break
        
        # Option 3: If API fails, try the memory hack
        if not content:
            print(f"  API read failed, trying memory hack...")
            # Try different filename variants
            for fname in ["SIDFILES.TXT", "SIDFILES.TXT.SEQ", "sidfiles.txt.seq"]:
                content = read_file_via_memory(base_path, fname, verbose=True)
                if content:
                    print(f"  ✓ Read via memory hack")
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
    
    try:
        while True:  # For loop mode
            playlist = sid_files.copy()
            if shuffle:
                random.shuffle(playlist)
            
            for i, sid_file in enumerate(playlist, 1):
                filename = sid_file.split('/')[-1]
                
                # Get SID info for duration
                if duration is None:
                    sid_info = get_sid_info(sid_file)
                    song_duration = sid_info['duration']
                else:
                    song_duration = duration
                
                print(f"\n[{i}/{len(playlist)}] {filename}")
                print(f"    Path: {sid_file}")
                print(f"    Duration: {format_duration(song_duration)}")
                
                if play_sid_file(sid_file, song_number):
                    print(f"    ▶ Playing...")
                    
                    # Wait for song duration with countdown
                    remaining = song_duration
                    while remaining > 0:
                        mins = remaining // 60
                        secs = remaining % 60
                        print(f"\r    ⏱ Remaining: {mins}:{secs:02d}  ", end='', flush=True)
                        time.sleep(1)
                        remaining -= 1
                    
                    print(f"\r    ✓ Finished                ")
                else:
                    print("    ✗ Skipping...")
                    time.sleep(2)
            
            if not loop:
                break
            
            print("\n" + "=" * 60)
            print("🔁 Restarting playlist...")
            print("=" * 60)
    
    except KeyboardInterrupt:
        print("\n\n⏹ Playback interrupted by user")
        stop_sid()
    
    print("\n" + "=" * 60)
    print("Finished!")


def main():
    global ULTIMATE_BASE_URL, API_BASE
    
    parser = argparse.ArgumentParser(
        description='Play SID files from SIDFILES.TXT on Ultimate64',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /USB0/MUSIC/HVSC/BESTOF
  %(prog)s /USB0/MUSIC/HVSC/BESTOF --random
  %(prog)s /USB0/MUSIC/HVSC/BESTOF --duration 120 --random --loop
  %(prog)s /USB0/MUSIC/HVSC/BESTOF --list-file /USB0/MUSIC/HVSC/BESTOF/SIDFILES.TXT

Note: Run sid_finder.prg on the C64 first to generate SIDFILES.TXT
        """
    )
    
    parser.add_argument('path', 
                        help='Base path to SID files directory on Ultimate (e.g., /USB0/MUSIC/HVSC/BESTOF)')
    
    parser.add_argument('--list-file', '-l',
                        help='Path to SIDFILES.TXT on Ultimate OR local file (default: <path>/SIDFILES.TXT)',
                        default=None)
    
    parser.add_argument('--local-list', '-L',
                        help='Use a local file for the SID list instead of reading from Ultimate',
                        default=None)
    
    parser.add_argument('--duration', '-d',
                        type=int,
                        help='Duration per song in seconds (default: auto-detect or 180)',
                        default=None)
    
    parser.add_argument('--song', '-s',
                        type=int,
                        help='Song number to play from each SID (default: 1)',
                        default=1)
    
    parser.add_argument('--random', '-r',
                        action='store_true',
                        help='Shuffle/randomize play order')
    
    parser.add_argument('--loop',
                        action='store_true',
                        help='Loop playlist forever')
    
    parser.add_argument('--host',
                        help=f'Ultimate device hostname/IP (default: {ULTIMATE_HOST})',
                        default=ULTIMATE_HOST)
    
    parser.add_argument('--port',
                        type=int,
                        help=f'Ultimate device port (default: {ULTIMATE_PORT})',
                        default=ULTIMATE_PORT)
    
    args = parser.parse_args()
    
    # Update config if custom host/port
    host = args.host
    port = args.port
    ULTIMATE_BASE_URL = f"http://{host}:{port}"
    API_BASE = f"{ULTIMATE_BASE_URL}/v1"
    
    # Determine list file path
    base_path = args.path.rstrip('/')
    if args.list_file:
        list_file = args.list_file
    else:
        # Try both with and without .SEQ extension (C64 sequential files)
        list_file = f"{base_path}/SIDFILES.TXT"
        # Will try .SEQ variant in play_all_sids if first fails
    
    play_all_sids(
        sid_list_path=list_file,
        base_path=base_path,
        duration=args.duration,
        song_number=args.song,
        shuffle=args.random,
        loop=args.loop,
        local_list=args.local_list
    )


if __name__ == "__main__":
    main()
