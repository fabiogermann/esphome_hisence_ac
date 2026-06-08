#!/usr/bin/env python3
"""
Analyze NEW checksum patterns to reverse engineer the algorithm
"""

# New data from the logs: (calculated_sum, received_checksum)
new_data = [
    (0x074C, 0x0631),  # diff = 0x011B
    (0x09AF, 0x062F),  # diff = 0x0380 (but this had malformed frame)
    (0x06B0, 0x0630),  # diff = 0x0080
    (0x08C3, 0x0630),  # diff = 0x0293
    (0x0721, 0x062F),  # diff = 0x00F2
]

print("Analyzing NEW checksum patterns...")
print("=" * 50)

# Look at the received checksums
print("\n1. Received checksum analysis:")
for calc, recv in new_data:
    print(f"  Calc: 0x{calc:04X}, Recv: 0x{recv:04X}, Diff: 0x{calc-recv:04X} ({calc-recv})")

# The received values are close: 0x062F, 0x0630, 0x0631
# This looks like a real checksum with small variations

# Check if it's the lower 12 bits
print("\n2. Lower 12 bits (& 0x0FFF):")
for calc, recv in new_data:
    lower12 = calc & 0x0FFF
    print(f"  Calc: 0x{calc:04X}, Lower12: 0x{lower12:04X}, Recv: 0x{recv:04X}, Match: {lower12 == recv}")

# Check if it's modulo some value
print("\n3. Modulo operations:")
for mod in [0x1000, 0x0800, 0x0700, 0x0680, 0x0640, 0x0632]:
    print(f"\n  Modulo 0x{mod:04X}:")
    for calc, recv in new_data:
        result = calc % mod
        print(f"    Calc: 0x{calc:04X} % 0x{mod:04X} = 0x{result:04X}, Recv: 0x{recv:04X}, Match: {result == recv}")

# Try different byte manipulations
print("\n4. Byte swapping and operations:")
for calc, recv in new_data:
    # Swap bytes
    swapped = ((calc & 0xFF) << 8) | ((calc >> 8) & 0xFF)
    print(f"  Calc: 0x{calc:04X}, Swapped: 0x{swapped:04X}, Recv: 0x{recv:04X}")

# Check if there's a pattern in the high/low bytes
print("\n5. High/Low byte analysis:")
for calc, recv in new_data:
    calc_high = (calc >> 8) & 0xFF
    calc_low = calc & 0xFF
    recv_high = (recv >> 8) & 0xFF
    recv_low = recv & 0xFF
    print(f"  Calc: H=0x{calc_high:02X} L=0x{calc_low:02X}, Recv: H=0x{recv_high:02X} L=0x{recv_low:02X}")

# The received checksums are all 0x062F, 0x0630, 0x0631
# They're very close to each other, differing by only 1-2
# The high byte is always 0x06

print("\n6. Pattern observation:")
print("  All received checksums have high byte = 0x06")
print("  Low bytes are: 0x2F, 0x30, 0x31 (consecutive values!)")
print("  This suggests the checksum might be based on a counter or specific bytes")

# Let's check if it could be sum of specific bytes only
print("\n7. Could it be sum of specific byte ranges?")
print("  If we assume only certain bytes are summed...")
print("  The received values 0x062F-0x0631 suggest a sum of ~1583-1585")

# Check if subtracting a constant gives us the pattern
print("\n8. Subtracting constants from calculated:")
for offset in [0x011B, 0x011C, 0x011D, 0x0080]:
    print(f"\n  Offset 0x{offset:04X}:")
    for calc, recv in new_data:
        result = calc - offset
        print(f"    Calc: 0x{calc:04X} - 0x{offset:04X} = 0x{result:04X}, Recv: 0x{recv:04X}, Close: {abs(result - recv) < 5}")

# Try XOR operations
print("\n9. XOR with constants:")
for xor_val in [0x0100, 0x0200, 0x0300, 0x0400, 0x0500, 0x0600]:
    matches = 0
    for calc, recv in new_data:
        result = calc ^ xor_val
        if abs(result - recv) < 10:
            matches += 1
    if matches > 2:
        print(f"  XOR with 0x{xor_val:04X}: {matches} close matches")

# The pattern seems to be that the checksum is around 0x0630
# with small variations based on the actual data
print("\n10. Hypothesis: Fixed base + variable component")
print("  Base: 0x0600")
print("  Variable: 0x2F-0x31 (based on specific data bytes)")

# Let's see if the low byte correlates with any simple calculation
print("\n11. Low byte correlation:")
for calc, recv in new_data:
    calc_low = calc & 0xFF
    recv_low = recv & 0xFF
    print(f"  Calc low: 0x{calc_low:02X}, Recv low: 0x{recv_low:02X}, " +
          f"Calc&0x3F: 0x{calc_low & 0x3F:02X}, Recv&0x3F: 0x{recv_low:02X}")