#!/usr/bin/env python3
"""Final checksum analysis to fix the remaining issues"""

def analyze_frame(hex_string):
    """Analyze a frame and calculate checksum"""
    # Parse hex string
    parts = hex_string.strip().split()
    data = [int(x, 16) for x in parts if x]
    
    print(f"Frame length: {len(data)} bytes")
    print(f"Header: {' '.join(f'{b:02X}' for b in data[:3])}")
    print(f"Type: {data[2]:02X} ({'Response' if data[2] == 0x01 else 'Command'})")
    
    # Find checksum position (before F4 FB)
    checksum_pos = len(data) - 4
    recv_checksum = (data[checksum_pos] << 8) | data[checksum_pos + 1]
    print(f"Received checksum: {recv_checksum:04X} at position {checksum_pos}")
    
    # Try different checksum calculations
    print("\nChecksum calculations:")
    
    # Method 1: Sum from index 2 (skip F4 F5)
    sum1 = sum(data[2:checksum_pos])
    print(f"1. Sum from index 2: {sum1:04X}")
    print(f"   With +1: {(sum1 + 1):04X}")
    
    # Method 2: Sum from index 3 (skip F4 F5 01)
    if data[2] == 0x01:
        sum2 = sum(data[3:checksum_pos])
        print(f"2. Sum from index 3: {sum2:04X}")
        print(f"   With +1: {(sum2 + 1):04X}")
    
    # Method 3: Sum from index 4
    sum3 = sum(data[4:checksum_pos])
    print(f"3. Sum from index 4: {sum3:04X}")
    print(f"   With +1: {(sum3 + 1):04X}")
    
    # Method 4: XOR based
    xor_val = 0
    for b in data[2:checksum_pos]:
        xor_val ^= b
    print(f"4. XOR from index 2: {xor_val:04X}")
    
    print("-" * 50)

# Analyze actual frames from the logs
print("COMMAND FRAME (Query):")
analyze_frame("F4 F5 00 40 0C 00 00 01 01 FE 01 00 00 66 00 00 00 01 B3 F4 FB")

print("\nSTATUS RESPONSE FRAME:")
analyze_frame("F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 01 00 28 16 15 16 80 80 00 01 61 00 00 00 00 00 00 00 00 00 00 80 01 00 00 00 00 00 1B 1A 1F 2B 00 00 FC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 05 BC F4 FB")

print("\nAnother STATUS RESPONSE:")
analyze_frame("F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 01 00 28 16 15 16 80 80 00 01 61 00 00 00 00 00 00 00 00 00 00 80 01 00 00 00 00 00 1B 1A 1E 2B 00 00 FC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 05 BB F4 FB")

print("\nAnother STATUS with different checksum:")
analyze_frame("F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 01 00 28 16 16 16 80 80 00 01 61 00 00 00 00 00 00 00 00 00 00 80 01 00 00 00 00 00 1C 1A 1F 2B 00 00 FC 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 05 BD F4 FB")