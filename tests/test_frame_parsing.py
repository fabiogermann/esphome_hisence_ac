"""Frame-level parser tests for :func:`tests.protocol.parse_frame`."""

from __future__ import annotations

import pytest

from tests import protocol


def test_roundtrip_build_then_parse(well_formed_frames):
    """``build_frame(payload)`` followed by ``parse_frame`` is the identity."""
    for case in well_formed_frames:
        raw = bytes.fromhex(case["hex"])
        payload = raw[:-4]
        rebuilt = protocol.build_frame(payload)
        assert rebuilt == raw, f"rebuild mismatch for {case['name']}"

        parsed = protocol.parse_frame(rebuilt)
        assert parsed.raw == raw
        assert parsed.checksum == int(case["expected_checksum"], 16)


def test_parse_accepts_known_good_query(well_formed_frames):
    case = next(f for f in well_formed_frames if f["name"] == "status_query")
    parsed = protocol.parse_frame(bytes.fromhex(case["hex"]))
    # First two body bytes encode the message version/length header
    assert parsed.body[0:2] == b"\x00\x40"


def test_parse_rejects_missing_header():
    bogus = b"\x00\x00\x00\x00\x00\xF4\xFB"
    with pytest.raises(protocol.FrameError, match="header"):
        protocol.parse_frame(bogus)


def test_parse_rejects_missing_footer():
    bogus = b"\xF4\xF5\x00\x40\x0C\x00\x00\x00"
    with pytest.raises(protocol.FrameError, match="footer"):
        protocol.parse_frame(bogus)


def test_parse_rejects_too_short():
    with pytest.raises(protocol.FrameError, match="too short"):
        protocol.parse_frame(b"\xF4\xF5")


def test_parse_rejects_bad_checksum(well_formed_frames):
    case = next(f for f in well_formed_frames if f["name"] == "status_query")
    raw = bytearray.fromhex(case["hex"])
    raw[-3] ^= 0xFF  # corrupt CS_lo
    with pytest.raises(protocol.FrameError, match="checksum mismatch"):
        protocol.parse_frame(bytes(raw))


def test_parse_rejects_truncated_real_world_capture(frames):
    """The truncated frame from output.txt MUST raise rather than crash."""
    case = next(f for f in frames if f["name"] == "truncated_frame_bug")
    with pytest.raises(protocol.FrameError):
        protocol.parse_frame(bytes.fromhex(case["hex"]))


def test_find_frame_end_locates_footer():
    junk = b"\x00\x01\x02"
    raw = junk + bytes.fromhex(
        "F4F500400C00000101FE0100006600000001B3F4FB"
    )
    end = protocol.find_frame_end(raw)
    assert end == len(raw)


def test_find_frame_end_returns_none_when_missing():
    assert protocol.find_frame_end(b"\xF4\xF5\x00\x00") is None
