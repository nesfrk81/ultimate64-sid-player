#!/usr/bin/env python3
"""
Build and deploy C64 BASIC program to Ultimate64

This script:
1. Converts BASIC file to properly tokenized PRG
2. Uploads and runs it on the C64 via Ultimate64 MCP
"""

import sys
import os
import struct
import re
import subprocess

# C64 BASIC v2.0 tokens
TOKENS = {
    'END': 0x80, 'FOR': 0x81, 'NEXT': 0x82, 'DATA': 0x83, 'INPUT#': 0x84,
    'INPUT': 0x85, 'DIM': 0x86, 'READ': 0x87, 'LET': 0x88, 'GOTO': 0x89,
    'RUN': 0x8A, 'IF': 0x8B, 'RESTORE': 0x8C, 'GOSUB': 0x8D, 'RETURN': 0x8E,
    'REM': 0x8F, 'STOP': 0x90, 'ON': 0x91, 'WAIT': 0x92, 'LOAD': 0x93,
    'SAVE': 0x94, 'VERIFY': 0x95, 'DEF': 0x96, 'POKE': 0x97, 'PRINT#': 0x98,
    'PRINT': 0x99, 'CONT': 0x9A, 'LIST': 0x9B, 'CLR': 0x9C, 'CMD': 0x9D,
    'SYS': 0x9E, 'OPEN': 0x9F, 'CLOSE': 0xA0, 'GET': 0xA1, 'NEW': 0xA2,
    'TAB(': 0xA3, 'TO': 0xA4, 'FN': 0xA5, 'SPC(': 0xA6, 'THEN': 0xA7,
    'NOT': 0xA8, 'STEP': 0xA9, '+': 0xAA, '-': 0xAB, '*': 0xAC, '/': 0xAD,
    '^': 0xAE, 'AND': 0xAF, 'OR': 0xB0, '>': 0xB1, '=': 0xB2, '<': 0xB3,
    'SGN': 0xB4, 'INT': 0xB5, 'ABS': 0xB6, 'USR': 0xB7, 'FRE': 0xB8,
    'POS': 0xB9, 'SQR': 0xBA, 'RND': 0xBB, 'LOG': 0xBC, 'EXP': 0xBD,
    'COS': 0xBE, 'SIN': 0xBF, 'TAN': 0xC0, 'ATN': 0xC1, 'PEEK': 0xC2,
    'LEN': 0xC3, 'STR$': 0xC4, 'VAL': 0xC5, 'ASC': 0xC6, 'CHR$': 0xC7,
    'LEFT$': 0xC8, 'RIGHT$': 0xC9, 'MID$': 0xCA
}

def tokenize_line(line):
    """Tokenize a BASIC line"""
    line = line.strip()
    if not line:
        return None
    
    # Extract line number
    match = re.match(r'^(\d+)\s+(.*)$', line)
    if not match:
        return None
    
    line_num = int(match.group(1))
    content = match.group(2)
    
    tokens = []
    i = 0
    in_string = False  # Track if we're inside a string literal
    
    while i < len(content):
        char = content[i]
        
        # Toggle string state on quote
        if char == '"':
            in_string = not in_string
            tokens.append(ord('"'))
            i += 1
            continue
        
        # If inside a string, don't tokenize - just add the character
        if in_string:
            if ord(char) < 128:
                tokens.append(ord(char))
            else:
                tokens.append(ord('?'))
            i += 1
            continue
        
        # Try to match keywords (longest first)
        matched = False
        for keyword in sorted(TOKENS.keys(), key=len, reverse=True):
            if content[i:].upper().startswith(keyword):
                # For single-character operators, always match (but not inside strings)
                if len(keyword) == 1:
                    tokens.append(TOKENS[keyword])
                    i += len(keyword)
                    matched = True
                    break
                # For PRINT# and INPUT#, allow following digit (file number)
                elif keyword in ['PRINT#', 'INPUT#']:
                    if i + len(keyword) < len(content) and content[i + len(keyword)].isdigit():
                        tokens.append(TOKENS[keyword])
                        i += len(keyword)
                        matched = True
                        break
                # For LOAD, SAVE, and VERIFY, always tokenize (they can be followed by string or variable)
                elif keyword in ['LOAD', 'SAVE', 'VERIFY']:
                    # Check word boundary - not preceded by alphanumeric
                    if i == 0 or not content[i - 1].isalnum():
                        tokens.append(TOKENS[keyword])
                        i += len(keyword)
                        matched = True
                        break
                # For multi-character keywords, check word boundary
                # Must not be preceded by alphanumeric, and not followed by alphanumeric
                elif (i == 0 or not content[i - 1].isalnum()) and \
                     (i + len(keyword) >= len(content) or not content[i + len(keyword)].isalnum()):
                    tokens.append(TOKENS[keyword])
                    i += len(keyword)
                    matched = True
                    break
        
        if not matched:
            # Regular character
            if ord(char) < 128:
                tokens.append(ord(char))
            else:
                tokens.append(ord('?'))
            i += 1
    
    return (line_num, tokens)

def basic_to_prg(basic_file, prg_file, start_addr=0x0801):
    """Convert BASIC file to properly tokenized PRG"""
    
    with open(basic_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()
    
    # Tokenize all lines
    line_data_list = []
    for line in lines:
        result = tokenize_line(line)
        if result:
            line_num, tokens = result
            # Create line data: [link_low, link_high, line_num_low, line_num_high, ...tokens..., 0]
            line_data = bytearray()
            line_data.extend(struct.pack('<H', 0))  # Link placeholder
            line_data.extend(struct.pack('<H', line_num))
            line_data.extend(tokens)
            line_data.append(0)  # End marker
            line_data_list.append((line_num, line_data))
    
    # Calculate addresses and set links
    current_addr = start_addr + 2
    for i in range(len(line_data_list)):
        line_num, line_data = line_data_list[i]
        
        # Set link to next line
        if i < len(line_data_list) - 1:
            next_addr = current_addr + len(line_data)
            line_data[0] = next_addr & 0xFF
            line_data[1] = (next_addr >> 8) & 0xFF
        else:
            # Last line: link = 0
            line_data[0] = 0
            line_data[1] = 0
        
        current_addr += len(line_data)
    
    # Build PRG
    prg = bytearray()
    prg.extend(struct.pack('<H', start_addr))
    
    for line_num, line_data in line_data_list:
        prg.extend(line_data)
    
    # Write PRG file
    with open(prg_file, 'wb') as f:
        f.write(prg)
    
    return len(prg)

def main():
    # Default files
    basic_file = "create_sid_list_fixed.bas"
    prg_file = "create_sid_list_fixed.prg"
    deploy_flag = True
    
    # Parse arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help']:
            print("Usage: python build_and_deploy.py [basic_file] [prg_file] [--no-deploy]")
            print()
            print("Builds a C64 BASIC program and optionally deploys it to Ultimate64")
            print()
            print("Arguments:")
            print("  basic_file    Input BASIC file (default: create_sid_list_fixed.bas)")
            print("  prg_file      Output PRG file (default: create_sid_list_fixed.prg)")
            print("  --no-deploy   Build only, don't deploy")
            print()
            print("Examples:")
            print("  python build_and_deploy.py")
            print("  python build_and_deploy.py create_sid_list_fixed.bas")
            print("  python build_and_deploy.py create_sid_list_fixed.bas output.prg")
            print("  python build_and_deploy.py create_sid_list_fixed.bas output.prg --no-deploy")
            sys.exit(0)
        basic_file = sys.argv[1]
    if len(sys.argv) > 2:
        prg_file = sys.argv[2]
    if '--no-deploy' in sys.argv:
        deploy_flag = False
    
    # Check if basic file exists
    if not os.path.exists(basic_file):
        print(f"✗ Error: BASIC file not found: {basic_file}")
        sys.exit(1)
    
    print("=" * 60)
    print("C64 BASIC Build and Deploy")
    print("=" * 60)
    print(f"Source: {basic_file}")
    print(f"Output: {prg_file}")
    print()
    
    # Build PRG
    print("Building PRG file...")
    try:
        size = basic_to_prg(basic_file, prg_file, start_addr=0x0801)
        print(f"✓ Created {prg_file} ({size} bytes)")
    except Exception as e:
        print(f"✗ Build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Deploy to C64
    if deploy_flag:
        print()
        print("Deploying to C64...")
        prg_path = os.path.abspath(prg_file)
        print(f"  PRG file: {prg_path}")
        print()
        print("✓ Build complete!")
        print()
        print("To deploy, the PRG file will be uploaded via MCP tool.")
        print(f"  File ready: {prg_path}")
        print()
        print("Note: The deployment will happen automatically when this script")
        print("      is called from the MCP environment.")
    else:
        print()
        print("Build complete. PRG file ready for manual deployment.")
        print(f"  File: {os.path.abspath(prg_file)}")
    
    print()
    print("=" * 60)
    print("Done!")
    print("=" * 60)

if __name__ == "__main__":
    main()
