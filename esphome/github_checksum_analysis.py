#!/usr/bin/env python3
"""
Analyze checksum based on GitHub issue #1 comment
https://github.com/straga/scrivo_project/issues/1#issuecomment-2208799644
"""

def analyze_checksum_methods(hex_string, name="Frame"):
    """Try different checksum calculation methods"""
    parts = hex_string.strip().split()
    data = [int(x, 16) for x in parts if x]
    
    print(f"\n{name}:")
    print(f"Length: {len(data)} bytes")
    
    # Find checksum position (2 bytes before F4 FB)
    checksum_pos = len(data) - 4
    recv_checksum = (data[checksum_pos] << 8) | data[checksum_pos + 1]
    print(f"Received checksum: 0x{recv_checksum:04X}")
    
    # Method 1: Simple sum from different positions
    for start in [0, 2, 3, 4]:
        total = sum(data[start:checksum_pos])
        print(f"Sum from index {start}: 0x{total:04X} (match: {total == recv_checksum})")
    
    # Method 2: Sum with modulo
    for start in [0, 2, 3]:
        total = sum(data[start:checksum_pos]) & 0xFFFF
        print(f"Sum from index {start} (mod 0xFFFF): 0x{total:04X} (match: {total == recv_checksum})")
    
    # Method 3: Check if length byte affects calculation
    if len(data) > 4:
        # Some protocols include/exclude length in checksum
        length_byte = data[4] if len(data) > 4 else 0
        
        # Try without length byte
        sum_no_len = sum(data[2:4]) + sum(data[5:checksum_pos])
        print(f"Sum skip length byte: 0x{sum_no_len:04X} (match: {sum_no_len == recv_checksum})")
        
        # Try special handling for type byte
        if data[2] == 0x01:  # Response
            sum_special = sum(data[3:checksum_pos])
            print(f"Response sum from 3: 0x{sum_special:04X} (match: {sum_special == recv_checksum})")
    
    # Method 4: Check byte-by-byte what makes the difference
    print("\nDetailed byte analysis:")
    running_sum = 0
    for i in range(2, min(10, checksum_pos)):
        running_sum += data[i]
        print(f"  [{i:2d}] = 0x{data[i]:02X}, sum = 0x{running_sum:04X}")

# Test with the query command
print("=" * 60)
print("QUERY COMMAND (should have checksum 0x01B3):")
analyze_checksum_methods(
    "F4 F5 00 40 0C 00 00 01 01 FE 01 00 00 66 00 00 00 01 B3 F4 FB",
    "Query Command"
)

# Test with status responses
print("\n" + "=" * 60)
print("STATUS RESPONSES:")

# Response 1 - checksum should be 0x05BC
analyze_checksum_methods(
    "F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 01 00 28 16 15 16 80 80 00 01 61 00 00 00 00 00 00 00 00 00 00 80 01 00 00 00 00 00 1B 1A 1F 2B 00 00 FC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 05 BC F4 FB",
    "Status Response 1 (0x05BC)"
)

# Let's check if there's a pattern with the message type
print("\n" + "=" * 60)
print("PATTERN ANALYSIS:")

# From the GitHub issue, it seems the checksum might be:
# For commands: sum from index 2
# For responses: sum from index 2 (not 3!)

test_frames = [
    ("F4 F5 00 40 0C 00 00 01 01 FE 01 00 00 66 00 00 00 01 B3 F4 FB", "Command", 0x01B3),
    ("F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 01 00 28 16 15 16 80 80 00 01 61 00 00 00 00 00 00 00 00 00 00 80 01 00 00 00 00 00 1B 1A 1F 2B 00 00 FC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 05 BC F4 FB", "Response", 0x05BC),
]

for frame_hex, frame_type, expected_checksum in test_frames:
    parts = frame_hex.strip().split()
    data = [int(x, 16) for x in parts if x]
    checksum_pos = len(data) - 4
    
    # Calculate from index 2
    calc_sum = sum(data[2:checksum_pos])
    
    print(f"\n{frame_type}:")
    print(f"  Expected: 0x{expected_checksum:04X}")
    print(f"  Calculated: 0x{calc_sum:04X}")
    print(f"  Match: {calc_sum == expected_checksum}")
    
    # If not matching, find the difference
    if calc_sum != expected_checksum:
        diff = expected_checksum - calc_sum
        print(f"  Difference: {diff} (0x{diff:04X})")

print("\n" + "=" * 60)
print("CONCLUSION:")
print("The checksum is the simple sum of bytes from index 2 to checksum position")
print("No +1 adjustment, no special handling for message types")