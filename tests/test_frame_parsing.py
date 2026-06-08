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


# ---------------------------------------------------------------------------
# Lenient parser: doubled-F4 corruption recovery
# ---------------------------------------------------------------------------

def test_strict_rejects_doubled_f4_corruption(frames):
    """The 83-byte ``... F4 F4 F4 FB`` capture must fail strict parsing."""
    case = next(f for f in frames if f["name"] == "doubled_f4_corruption")
    raw = bytes.fromhex(case["hex"])
    assert len(raw) == 83
    assert raw[-4:] == b"\xF4\xF4\xF4\xFB"
    with pytest.raises(protocol.FrameError, match="checksum"):
        protocol.parse_frame(raw)


def test_lenient_recovers_doubled_f4_corruption(frames):
    """parse_frame_lenient drops one F4 and revalidates -> CS 0x06F4."""
    case = next(f for f in frames if f["name"] == "doubled_f4_corruption")
    raw = bytes.fromhex(case["hex"])
    parsed = protocol.parse_frame_lenient(raw)
    assert parsed.checksum == int(case["recovered_checksum"], 16)
    # Recovered payload is the 76-byte body (82-byte raw minus 2 header,
    # 2 CS, 2 footer). On status RESPONSE frames body[0] == 0x01 and the
    # message-type marker at body[11] is 0x66 (matches the other captured
    # response fixtures - see status_response_temp19 etc).
    assert len(parsed.payload) == 76
    assert parsed.payload[0] == 0x01
    assert parsed.payload[11] == protocol.MSG_QUERY


def test_lenient_matches_strict_on_clean_frames(well_formed_frames):
    """parse_frame_lenient must not change behaviour on well-formed input."""
    for case in well_formed_frames:
        raw = bytes.fromhex(case["hex"])
        strict = protocol.parse_frame(raw)
        lenient = protocol.parse_frame_lenient(raw)
        assert strict.checksum == lenient.checksum
        assert strict.payload == lenient.payload


def test_lenient_does_not_mask_real_checksum_errors(well_formed_frames):
    """A genuine single-byte corruption (not the F4 F4 FB pattern) still raises."""
    case = next(f for f in well_formed_frames if f["name"] == "status_query")
    raw = bytearray.fromhex(case["hex"])
    raw[-5] ^= 0xFF  # corrupt one body byte
    with pytest.raises(protocol.FrameError, match="checksum"):
        protocol.parse_frame_lenient(bytes(raw))
