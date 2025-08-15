#!/usr/bin/env python3
"""
Analyze checksum patterns to reverse engineer the algorithm
"""

# Data from the logs: (calculated_sum, received_checksum)
data_points = [
    (0x0677, 0x05BE),
    (0x05CD, 0x05BD),
    (0x05C0, 0x05BD),
    (0x05C1, 0x05BE),
    (0x08C9, 0x05BE),
    (0x0602, 0x05BF),
    (0x0597, 0x05BF),
    (0x06B0, 0x05BE),
    (0x0606, 0x05BE),
    (0x0710, 0x05BF),
    (0x0630, 0x05BE),
    (0x071B, 0x05BF),
]

print("Analyzing checksum patterns...")
print("=" * 50)

# Check if it's just the lower byte
print("\n1. Lower byte of calculated sum:")
for calc, recv in data_points:
    lower = calc & 0xFF
    print(f"  Calc: 0x{calc:04X}, Recv: 0x{recv:04X}, Lower: 0x{lower:02X}, Match: {lower == (recv & 0xFF)}")

# Check if it's modulo some value
print("\n2. Modulo operations:")
for mod in [3, 4, 5, 8, 16, 32, 64, 128, 256]:
    matches = 0
    for calc, recv in data_points:
        if (calc % mod) == (recv % mod):
            matches += 1
    if matches > len(data_points) // 2:
        print(f"  Modulo {mod}: {matches}/{len(data_points)} matches")

# Check if there's a pattern in the differences
print("\n3. Difference analysis:")
for calc, recv in data_points:
    diff = calc - recv
    print(f"  Calc: 0x{calc:04X}, Recv: 0x{recv:04X}, Diff: 0x{diff:04X} ({diff})")

# Check if only certain bits are used
print("\n4. Bit pattern analysis:")
print("  Received values in binary:")
for _, recv in data_points:
    print(f"    0x{recv:04X} = {bin(recv)[2:].zfill(16)}")

# Check if it's related to XOR with a constant
print("\n5. XOR with constants:")
for xor_val in [0x0500, 0x05FF, 0x05AA, 0x0555]:
    print(f"  XOR with 0x{xor_val:04X}:")
    for calc, recv in data_points[:3]:
        result = calc ^ xor_val
        print(f"    Calc: 0x{calc:04X} ^ 0x{xor_val:04X} = 0x{result:04X}, Recv: 0x{recv:04X}")

# Check if the checksum is actually just counting specific values
print("\n6. Received checksum frequency:")
checksum_counts = {}
for _, recv in data_points:
    checksum_counts[recv] = checksum_counts.get(recv, 0) + 1
for checksum, count in sorted(checksum_counts.items()):
    print(f"  0x{checksum:04X}: {count} times")

# Look for patterns in the last two digits
print("\n7. Pattern in lower byte of received (0xBD, 0xBE, 0xBF):")
for calc, recv in data_points:
    lower_recv = recv & 0xFF
    lower_calc = calc & 0xFF
    print(f"  Calc lower: 0x{lower_calc:02X}, Recv lower: 0x{lower_recv:02X}, " +
          f"Calc & 0x03: {calc & 0x03}, Recv & 0x03: {recv & 0x03}")

# The pattern seems to be that received is always 0x05BD, 0x05BE, or 0x05BF
# This is 0x0500 + (0xBD, 0xBE, or 0xBF)
# Let's check if it's related to the lower 2 bits
print("\n8. Checksum might be 0x0500 + (calculated & 0x03) + 0xBD:")
for calc, recv in data_points:
    predicted = 0x0500 + (calc & 0x03) + 0xBD
    if predicted > 0x05BF:
        predicted = 0x05BD + ((predicted - 0x05BD) % 3)
    print(f"  Calc: 0x{calc:04X}, Predicted: 0x{predicted:04X}, Recv: 0x{recv:04X}, " +
          f"Match: {predicted == recv}")

# Another approach - maybe it's just the sum modulo 3
print("\n9. Checksum as 0x05BD + (sum % 3):")
for calc, recv in data_points:
    predicted = 0x05BD + (calc % 3)
    print(f"  Calc: 0x{calc:04X}, Predicted: 0x{predicted:04X}, Recv: 0x{recv:04X}, " +
          f"Match: {predicted == recv}")