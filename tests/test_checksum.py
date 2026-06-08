"""Verify the Hisense 16-bit checksum against real captured frames."""

from __future__ import annotations

import pytest

from tests import protocol


@pytest.mark.parametrize(
    "case_id,expected",
    [
        ("status_query", 0x01B3),
        ("status_response_temp19", 0x04C3),
        ("status_response_temp20", 0x04C4),
    ],
)
def test_checksum_matches_embedded(well_formed_frames, case_id, expected):
    """Every well-formed captured frame's checksum matches our algorithm."""
    case = next(f for f in well_formed_frames if f["name"] == case_id)
    raw = bytes.fromhex(case["hex"])
    payload = raw[:-4]  # strip CS bytes + footer
    assert protocol.checksum(payload) == expected
    assert protocol.checksum_bytes(payload) == raw[-4:-2]


def test_checksum_is_big_endian():
    """High byte must come first on the wire."""
    payload = bytes.fromhex("F4F500400C00000101FE0100006600000000")
    cs = protocol.checksum(payload)
    cs_bytes = protocol.checksum_bytes(payload)
    assert cs_bytes[0] == (cs >> 8) & 0xFF
    assert cs_bytes[1] == cs & 0xFF


def test_mutating_payload_breaks_checksum(well_formed_frames):
    """Flipping any payload byte must change the checksum."""
    case = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )
    raw = bytearray.fromhex(case["hex"])
    original_cs = protocol.checksum(bytes(raw[:-4]))
    raw[18] ^= 0xFF
    mutated_cs = protocol.checksum(bytes(raw[:-4]))
    assert mutated_cs != original_cs


def test_checksum_skips_header_bytes():
    """The first two bytes (F4 F5) MUST be excluded from the sum."""
    payload = b"\xF4\xF5\x01\x02\x03"
    assert protocol.checksum(payload) == 0x01 + 0x02 + 0x03


def test_checksum_wraps_at_16_bits():
    """The result is masked to 16 bits."""
    body = b"\xFF" * 300  # 300 * 255 = 76500 > 0xFFFF
    payload = b"\xF4\xF5" + body
    assert protocol.checksum(payload) == 76500 & 0xFFFF
