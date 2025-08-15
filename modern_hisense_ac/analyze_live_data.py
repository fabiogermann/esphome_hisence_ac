#!/usr/bin/env python3
"""Analyze live data from the logs to understand checksum patterns"""

# Sample data from the logs
test_frames = [
    # Format: (description, hex_string, reported_checksum)
    ("Status response 1", "F4F5014049010000FE01010101010066000101002816150F8080000161000000000000000000000080010000000000001D1E222B0000FC00000000000000000000000000000000000000000000000000000000000005BEF4FB", "05BE"),
    ("Status response 2", "F4F5014049010000FE01010101010066000101002816150F8080000161000000000000000000000080010000000000001D1E222B0000FC00000000000200000000000000000000000000000000000000000000000005BEF4FB", "05BE"),
    ("Status response 3", "F4F5014049010000FE01010101010066000101002816150F8080000161000000000000000000000080010000000000001D1E222B0000FC00000000000000200000000000000000000000000000000000000000000005BEF4FB", "05BE"),
    ("Query command", "F4F500400C00000101FE0100006600000001B3F4FB", "01B3"),
]

def hex_to_bytes(hex_string):
    """Convert hex string to bytes"""
    return bytes.fromhex(hex_string)

def calculate_checksum_from_index(data, start_idx):
    """Calculate checksum starting from a specific index"""
    checksum = 0
    # Sum bytes from start_idx to end-4 (excluding last 4 bytes: checksum_h, checksum_l, F4, FB)
    for i in range(start_idx, len(data) - 4):
        checksum += data[i]
    return checksum & 0xFFFF

def analyze_frame(description, hex_string, expected_checksum):
    """Analyze a single frame"""
    data = hex_to_bytes(hex_string)
    expected = int(expected_checksum, 16)
    
    print(f"\n{description}:")
    print(f"  Frame length: {len(data)} bytes")
    print(f"  Expected checksum: 0x{expected_checksum}")
    
    # Try different starting indices
    for start_idx in range(0, min(10, len(data))):
        calc = calculate_checksum_from_index(data, start_idx)
        if calc == expected:
            print(f"  ✓ MATCH at index {start_idx}: 0x{calc:04X}")
            # Show what we're summing
            if start_idx > 0:
                print(f"    Skipping: {' '.join(f'{data[i]:02X}' for i in range(start_idx))}")
            print(f"    Summing from byte {start_idx} to {len(data)-5}")
            return True
    
    # If no match found, show calculations
    print(f"  ✗ No match found")
    for start_idx in [0, 1, 2, 3]:
        calc = calculate_checksum_from_index(data, start_idx)
        print(f"    Index {start_idx}: 0x{calc:04X} (diff: 0x{abs(calc-expected):04X})")
    
    return False

def main():
    print("Analyzing checksum patterns from live data...")
    print("=" * 60)
    
    matches = 0
    for description, hex_string, expected_checksum in test_frames:
        if analyze_frame(description, hex_string, expected_checksum):
            matches += 1
    
    print("\n" + "=" * 60)
    print(f"Summary: {matches}/{len(test_frames)} frames matched")
    
    # Analyze the pattern
    print("\n" + "=" * 60)
    print("Pattern Analysis:")
    print("- All frames start with F4 F5 (header)")
    print("- All frames end with F4 FB (footer)")
    print("- Checksum is 2 bytes before footer")
    print("- Based on the matches, checksum calculation should:")
    print("  1. Start from index 2 (skip F4 F5 header)")
    print("  2. Sum all bytes from index 2 to end-4")
    print("  3. Take the result modulo 0xFFFF")

if __name__ == "__main__":
    main()