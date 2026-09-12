"""Streaming-parser tests that pin down the Home Assistant init bug.

Background
----------
The captured ``output.txt`` log shows the Home Assistant climate entity never
finishes initialising: the firmware fires a status query every ~10 s but the
parser flags PARSE_ERROR on every response and clears its receive buffer,
losing the next frame's header.

The root cause is that ``parse_ac_message_byte_()`` in air_conditioner.cpp
treats the rx_buffer as if it always starts with ``F4 F5``. When a stray
byte arrives (line noise, mid-frame fragment, a trailing byte from a previous
response), the parser logs *"Wrong magic start sequence"* and clears the
entire buffer - including any subsequent ``F4 F5`` bytes that are already
queued up. The firmware never re-syncs and HA never sees an "online" entity.

These tests assert what a *resync-safe* parser MUST do. The pure-Python
:class:`StreamingParser` is the executable specification; the C++ code must
be brought into line with it to fix the bug.
"""

from __future__ import annotations

from tests import protocol


# ---------------------------------------------------------------------------
# Basic feeding and reset
# ---------------------------------------------------------------------------

def test_streaming_parser_accepts_known_good_query(well_formed_frames):
    case = next(f for f in well_formed_frames if f["name"] == "status_query")
    raw = bytes.fromhex(case["hex"])

    parser = protocol.StreamingParser()
    frames = parser.feed(raw)

    assert len(frames) == 1
    assert frames[0].raw == raw
    assert parser.drops == 0


def test_streaming_parser_accepts_byte_at_a_time(well_formed_frames):
    """The real UART delivers one byte at a time on slow ESP-01 builds."""
    case = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )
    raw = bytes.fromhex(case["hex"])

    parser = protocol.StreamingParser()
    yielded: list[protocol.Frame] = []
    for b in raw:
        yielded.extend(parser.feed(bytes([b])))

    assert len(yielded) == 1
    assert yielded[0].raw == raw


def test_streaming_parser_resyncs_after_garbage_prefix(well_formed_frames):
    """Random bytes BEFORE a valid frame must not break recognition.

    This is the precise scenario from the output.txt log at 08:56:28: the AC
    sends 70 bytes of stuff with no leading F4 F5, followed by a real frame.
    A resync-safe parser drops the noise and emits the next valid frame.
    """
    case = next(f for f in well_formed_frames if f["name"] == "status_query")
    valid = bytes.fromhex(case["hex"])
    garbage = bytes.fromhex("0101010100660001000030151715808000")

    parser = protocol.StreamingParser()
    frames = parser.feed(garbage + valid)

    assert len(frames) == 1
    assert frames[0].raw == valid
    assert parser.drops == len(garbage)


def test_streaming_parser_handles_back_to_back_frames(well_formed_frames):
    case_a = next(f for f in well_formed_frames if f["name"] == "status_query")
    case_b = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )
    a = bytes.fromhex(case_a["hex"])
    b = bytes.fromhex(case_b["hex"])

    parser = protocol.StreamingParser()
    frames = parser.feed(a + b)

    assert len(frames) == 2
    assert frames[0].raw == a
    assert frames[1].raw == b


def test_streaming_parser_drops_truncated_frame_and_recovers(
    frames, well_formed_frames
):
    """The truncated 16-byte fragment must not block the next real frame.

    Mirrors output.txt 08:57:13 (truncated) + 08:58:00 (real frame).
    """
    truncated_case = next(
        f for f in frames if f["name"] == "truncated_frame_bug"
    )
    valid_case = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )

    truncated = bytes.fromhex(truncated_case["hex"])
    valid = bytes.fromhex(valid_case["hex"])

    parser = protocol.StreamingParser()
    result = parser.feed(truncated + valid)

    assert len(result) == 1, (
        "the truncated fragment must be discarded, but the real frame after "
        "it must still be emitted - this is the HA-init bug"
    )
    assert result[0].raw == valid


def test_streaming_parser_drops_checksum_mismatch_and_recovers(
    well_formed_frames,
):
    """A corrupted frame must not poison the next valid one."""
    case = next(f for f in well_formed_frames if f["name"] == "status_query")
    raw = bytearray.fromhex(case["hex"])
    raw[-3] ^= 0xFF  # corrupt CS_lo
    corrupted = bytes(raw)

    valid = bytes.fromhex(case["hex"])

    parser = protocol.StreamingParser()
    result = parser.feed(corrupted + valid)

    assert len(result) == 1
    assert result[0].raw == valid


def test_streaming_parser_handles_real_world_log_sequence(
    frames, well_formed_frames
):
    """Replay an output.txt-style stream and assert HA-visible frames count.

    The bug under test: in the live log, ~10 well-formed frames pass through
    the UART each minute and HA still never initialises. A correct parser
    fed the same stream MUST emit a Frame for each.
    """
    # Sequence: garbage_a + (real frame) + truncated + (real frame) + garbage_b
    garbage_a = bytes.fromhex(
        next(f["hex"] for f in frames if f["name"] == "headerless_fragment_a")
    )
    garbage_b = bytes.fromhex(
        next(f["hex"] for f in frames if f["name"] == "headerless_fragment_b")
    )
    truncated = bytes.fromhex(
        next(f["hex"] for f in frames if f["name"] == "truncated_frame_bug")
    )
    real_a = bytes.fromhex(
        next(
            f["hex"]
            for f in well_formed_frames
            if f["name"] == "status_response_temp19"
        )
    )
    real_b = bytes.fromhex(
        next(
            f["hex"]
            for f in well_formed_frames
            if f["name"] == "status_response_temp20"
        )
    )

    stream = garbage_a + real_a + truncated + real_b + garbage_b

    parser = protocol.StreamingParser()
    out = parser.feed(stream)

    assert len(out) == 2, (
        "Two well-formed frames are buried in this stream. Without resync, "
        "the firmware sees zero - hence HA never initialises."
    )
    assert out[0].raw == real_a
    assert out[1].raw == real_b


# ---------------------------------------------------------------------------
# Defensive limits
# ---------------------------------------------------------------------------

def test_streaming_parser_caps_runaway_buffer():
    """A header without a footer must not grow the buffer unboundedly."""
    parser = protocol.StreamingParser()
    parser.feed(b"\xF4\xF5" + b"\x00" * 500)
    assert len(parser) <= parser.MAX_FRAME_SIZE


def test_streaming_parser_idempotent_reset():
    parser = protocol.StreamingParser()
    parser.feed(b"\xF4\xF5\x00\x00")
    parser.reset()
    assert len(parser) == 0
    assert parser.state is protocol.StreamingState.SEEK_F4


# ---------------------------------------------------------------------------
# RX de-stuffing (units that double literal 0xF4 on TX; upstream 8eb76f2
# / e5a3ee3). Backwards compatible: raw frames take pass 1, only checksum
# failures fall into the de-stuffed pass 2.
# ---------------------------------------------------------------------------

# Status-response-like body with literal 0xF4 bytes inside.
BODY_WITH_F4S = bytes([
    0x01, 0x40, 0x49, 0x01, 0x00, 0x66, 0x00, 0x01,
    0xF4, 0x10, 0xF4, 0x20, 0x25, 0x80, 0x42, 0x03,
])
BODY_NO_F4 = bytes([
    0x01, 0x40, 0x49, 0x01, 0x00, 0x66, 0x00, 0x01,
    0x10, 0x20, 0x25, 0x80, 0x42, 0x03, 0x11, 0x22,
])


def test_destuffed_frame_recovered():
    """A fully stuffed frame is de-stuffed and accepted."""
    wire = protocol.build_wire_frame(protocol.HEADER + BODY_WITH_F4S)
    assert wire != protocol.HEADER + BODY_WITH_F4S + \
        protocol.checksum_bytes(protocol.HEADER + BODY_WITH_F4S) + \
        protocol.FOOTER  # stuffing actually kicked in
    parser = protocol.StreamingParser()
    out = parser.feed(wire)
    assert len(out) == 1
    assert out[0].payload == BODY_WITH_F4S


def test_unstuffed_frame_bit_identical():
    """Pass 1 must accept raw frames unchanged (backwards compatible)."""
    raw = protocol.build_frame(protocol.HEADER + BODY_NO_F4)
    parser = protocol.StreamingParser()
    out = parser.feed(raw)
    assert len(out) == 1
    assert out[0].raw == raw
    assert out[0].payload == BODY_NO_F4


def _find_body_with_low_cs(byte: int, body: bytearray) -> bytearray:
    """Return ``body`` mutated so sum(body) & 0xFF == ``byte``."""
    base = sum(body[:-1]) & 0xFF
    body[-1] = (byte - base) & 0xFF
    return body


def test_destuffed_checksum_bytes_recovered():
    """Checksum bytes that are themselves 0xF4 pass after de-stuffing."""
    body = _find_body_with_low_cs(0xF4, bytearray(BODY_NO_F4))
    # Wire ends: body... cs_hi F4 F4 (stuffed cs_lo) F4 FB
    wire = protocol.build_wire_frame(protocol.HEADER + bytes(body))
    raw = protocol.build_frame(protocol.HEADER + bytes(body))
    assert len(wire) == len(raw) + 1  # exactly one stuffed byte (cs_lo)
    parser = protocol.StreamingParser()
    out = parser.feed(wire)
    assert len(out) == 1
    assert out[0].payload == bytes(body)


def test_doubled_f4_before_footer_recovered():
    """Stuffed final body byte + stuffed cs collapse correctly."""
    body = _find_body_with_low_cs(0xF4, bytearray([0x01, 0x10, 0x20]))
    wire = protocol.build_wire_frame(protocol.HEADER + bytes(body))
    raw = protocol.build_frame(protocol.HEADER + bytes(body))
    assert len(wire) == len(raw) + 1
    parser = protocol.StreamingParser()
    out = parser.feed(wire)
    assert len(out) == 1
    assert out[0].payload == bytes(body)


def test_destuff_still_rejects_garbage():
    """Garbage failing both passes is still dropped with clean resync."""
    good = protocol.build_frame(protocol.HEADER + BODY_NO_F4)
    garbage = b"\xF4\xF5\x01\x02\x03\x00\x00\xF4\xFB"
    parser = protocol.StreamingParser()
    out = parser.feed(garbage + good)
    assert len(out) == 1
    assert out[0].raw == good
