#!/usr/bin/env python3
"""
C64 BASIC to PRG converter
Converts BASIC source code to C64 PRG format with proper tokenization
"""

import struct
import re
import sys

# C64 BASIC token values
BASIC_TOKENS = {
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

def tokenize_basic_line(line):
    """Convert a BASIC line to tokenized format"""
    # Remove line number (we'll add it separately)
    line = line.strip()
    if not line:
        return None
    
    # Extract line number
    match = re.match(r'^(\d+)\s*(.*)$', line)
    if not match:
        return None
    
    line_num = int(match.group(1))
    content = match.group(2)
    
    tokens = []
    
    # Tokenize the content
    i = 0
    in_string = False
    in_rem = False
    
    while i < len(content):
        char = content[i]
        
        # Track string literals - don't tokenize inside them
        if char == '"':
            in_string = not in_string
            tokens.append(ord(char))
            i += 1
            continue
        
        # If we're inside a string or after REM, just add raw character
        if in_string or in_rem:
            if ord(char) < 128:
                tokens.append(ord(char))
            else:
                tokens.append(ord('?'))
            i += 1
            continue
        
        # Try to match BASIC keywords (longest first)
        matched = False
        for keyword in sorted(BASIC_TOKENS.keys(), key=len, reverse=True):
            if content[i:].upper().startswith(keyword):
                # For single-char operators, always tokenize
                if len(keyword) == 1 and keyword in '+-*/^>=<':
                    tokens.append(BASIC_TOKENS[keyword])
                    i += len(keyword)
                    matched = True
                    break
                # PRINT# and INPUT# are followed by file number directly
                elif keyword in ('PRINT#', 'INPUT#'):
                    tokens.append(BASIC_TOKENS[keyword])
                    i += len(keyword)
                    matched = True
                    break
                # For keywords, check word boundary
                elif len(keyword) > 1:
                    end_pos = i + len(keyword)
                    if end_pos >= len(content) or not content[end_pos].isalnum():
                        tokens.append(BASIC_TOKENS[keyword])
                        i += len(keyword)
                        matched = True
                        # Check if this was REM - rest of line is comment
                        if keyword == 'REM':
                            in_rem = True
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
    """Convert BASIC file to PRG format"""
    
    with open(basic_file, 'r', encoding='latin-1') as f:
        lines = f.readlines()
    
    prg_data = bytearray()
    
    # Add load address
    prg_data.extend(struct.pack('<H', start_addr))
    
    # Process each line
    prev_line_addr = start_addr + 2
    line_data_list = []
    
    for line in lines:
        line = line.rstrip('\r\n')
        if not line.strip():
            continue
        
        result = tokenize_basic_line(line)
        if result is None:
            continue
        
        line_num, tokens = result
        
        # Calculate line data
        # Format: [link_low, link_high, line_num_low, line_num_high, ...tokens..., 0]
        line_data = bytearray()
        line_data.extend(struct.pack('<H', 0))  # Link (will be filled later)
        line_data.extend(struct.pack('<H', line_num))
        line_data.extend(tokens)
        line_data.append(0)  # End of line marker
        
        line_data_list.append((prev_line_addr, line_data))
        prev_line_addr += len(line_data)
    
    # Set links between lines
    for i in range(len(line_data_list) - 1):
        current_addr, current_data = line_data_list[i]
        next_addr, _ = line_data_list[i + 1]
        # Set link in current line
        current_data[0] = next_addr & 0xFF
        current_data[1] = (next_addr >> 8) & 0xFF
    
    # Last line has link = 0
    if line_data_list:
        last_addr, last_data = line_data_list[-1]
        last_data[0] = 0
        last_data[1] = 0
    
    # Add all line data
    for addr, data in line_data_list:
        prg_data.extend(data)
    
    # Write PRG file
    with open(prg_file, 'wb') as f:
        f.write(prg_data)
    
    return len(prg_data)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python basic_tokenizer.py <basic_file> <prg_file>")
        sys.exit(1)
    
    basic_file = sys.argv[1]
    prg_file = sys.argv[2]
    
    print(f"Converting {basic_file} to {prg_file}...")
    size = basic_to_prg(basic_file, prg_file)
    print(f"Created {prg_file} ({size} bytes)")
