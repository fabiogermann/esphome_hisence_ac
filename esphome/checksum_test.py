#!/usr/bin/env python3
"""
Test script to verify checksum calculation approach
Reads test data from checksum_testdata.json and validates the algorithm
"""

import json
import sys

def calculate_checksum(hex_string):
    """Calculate checksum using the correct algorithm"""
    # Parse hex string
    parts = hex_string.strip().split()
    data = [int(x, 16) for x in parts if x]
    
    # Find checksum position (4 bytes from end)
    checksum_pos = len(data) - 4
    
    # Calculate sum from index 2 to checksum position
    calc_sum = sum(data[2:checksum_pos]) & 0xFFFF
    
    # Extract received checksum
    recv_checksum = (data[checksum_pos] << 8) | data[checksum_pos + 1]
    
    return calc_sum, recv_checksum

def run_tests(test_file='checksum_testdata.json'):
    """Run checksum tests from test data file"""
    print("=" * 60)
    print("CHECKSUM VALIDATION TEST")
    print("=" * 60)
    
    try:
        with open(test_file, 'r') as f:
            test_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Test data file '{test_file}' not found")
        return
    
    total_tests = len(test_data['frames'])
    passed = 0
    failed = 0
    
    print(f"\nRunning {total_tests} tests...\n")
    
    for i, frame_data in enumerate(test_data['frames'], 1):
        frame_type = frame_data['type']
        frame_hex = frame_data['hex']
        expected = frame_data['expected_checksum']
        source = frame_data.get('source', '')
        
        calc_checksum, recv_checksum = calculate_checksum(frame_hex)
        
        # Check if calculation matches expected
        if calc_checksum == expected:
            passed += 1
            status = "✓ PASS"
        else:
            failed += 1
            status = "✗ FAIL"
            
        # Check if received checksum matches expected
        recv_match = "✓" if recv_checksum == expected else "✗"
        
        print(f"Test {i:3d}: {status} | Type: {frame_type:8s} | "
              f"Calc: 0x{calc_checksum:04X} | "
              f"Recv: 0x{recv_checksum:04X} {recv_match} | "
              f"Expected: 0x{expected:04X}")
        
        if status == "✗ FAIL":
            print(f"         Source: {source}")
            print(f"         Frame: {frame_hex[:50]}...")
    
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed}/{total_tests} passed, {failed}/{total_tests} failed")
    
    if failed == 0:
        print("✓ All tests passed! Checksum algorithm is correct.")
    else:
        print(f"✗ {failed} tests failed. Algorithm needs adjustment.")
    
    print("=" * 60)
    
    return passed == total_tests

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)