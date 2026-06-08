"""Pin the command-frame format the firmware sends to the AC.

The historical implementation in the original repo (commit 42ebae2 in this
repo's git history, file ``hisense_ac.h``) used pre-canned constant frames
for each mode change. Those frames are known to work on real hardware,
so we use them as the source of truth here.

The new ``send_status`` in ``air_conditioner.cpp`` MUST emit the same
status[16] (command discriminator), status[17] ("change" flag),
status[18] (mode byte), status[19] (target temp) and status[31..35]
envelope bytes -- otherwise the AC silently ignores the command (the
symptom is "OFF -> FAN_ONLY works, FAN_ONLY -> COOL is ignored").

The fixtures below were captured verbatim from the historical
``hisense_ac.h`` and have all been re-verified against the
``protocol.checksum`` implementation.
"""

from __future__ import annotations

from tests import protocol


# ---------------------------------------------------------------------------
# Reference frames (from historical hisense_ac.h, byte-for-byte)
# ---------------------------------------------------------------------------

MODE_COOL = bytes([
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x01, 0x01, 0x50, 0x35, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x01,
    0x04, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x02, 0x7F, 0xF4, 0xFB,
])

MODE_HEAT = bytes([
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x01, 0x01, 0x30, 0x2F, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x01,
    0x04, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x02, 0x59, 0xF4, 0xFB,
])

MODE_FAN = bytes([
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x07, 0x01, 0x10, 0x33, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x01,
    0x04, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x02, 0x43, 0xF4, 0xFB,
])

MODE_DRY = bytes([
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x01, 0x01, 0x70, 0x33, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x01,
    0x04, 0x00, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x02, 0x9D, 0xF4, 0xFB,
])

TEMP_25 = bytes([
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x33, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x02, 0x06, 0xF4, 0xFB,
])


# ---------------------------------------------------------------------------
# Checksum sanity (catches typos in the reference frames above)
# ---------------------------------------------------------------------------

def test_reference_mode_cool_checksum_valid():
    f = protocol.parse_frame(MODE_COOL)
    assert f.checksum == 0x027F


def test_reference_mode_heat_checksum_valid():
    f = protocol.parse_frame(MODE_HEAT)
    assert f.checksum == 0x0259


def test_reference_mode_fan_checksum_valid():
    f = protocol.parse_frame(MODE_FAN)
    assert f.checksum == 0x0243


def test_reference_mode_dry_checksum_valid():
    f = protocol.parse_frame(MODE_DRY)
    assert f.checksum == 0x029D


def test_reference_temp_25_checksum_valid():
    f = protocol.parse_frame(TEMP_25)
    assert f.checksum == 0x0206


# ---------------------------------------------------------------------------
# Mode-byte invariants
# ---------------------------------------------------------------------------

def test_mode_cool_payload_byte_layout():
    """status[16]=0x01 (mode-change), [17]=0x01 (active), [18]=0x50 (cool)."""
    # status[i] -> frame[i] (since frame[0..1] is the F4F5 header but the
    # "status" array in the C++ code includes the header at indices 0,1).
    assert MODE_COOL[16] == 0x01
    assert MODE_COOL[17] == 0x01
    assert MODE_COOL[18] == 0x50
    # Target temp byte: 26 C -> (26<<1)|1 = 53 = 0x35
    assert MODE_COOL[19] == 0x35
    assert (MODE_COOL[19] >> 1) == 26


def test_mode_fan_payload_byte_layout():
    """FAN_ONLY uses a DIFFERENT command discriminator (0x07, not 0x01)."""
    assert MODE_FAN[16] == 0x07
    assert MODE_FAN[17] == 0x01
    assert MODE_FAN[18] == 0x10
    assert (MODE_FAN[19] >> 1) == 25  # 0x33 -> 25 C


def test_mode_change_envelope_bytes():
    """status[31..35] = 10 01 04 00 10 for every mode-change frame."""
    for f in (MODE_COOL, MODE_HEAT, MODE_FAN, MODE_DRY):
        assert f[31] == 0x10
        assert f[32] == 0x01
        assert f[33] == 0x04
        assert f[34] == 0x00
        assert f[35] == 0x10


def test_temp_only_frame_has_no_mode_envelope():
    """Pure temp command sets status[16..18] all 0 and clears the envelope."""
    assert TEMP_25[16] == 0x00
    assert TEMP_25[17] == 0x00
    assert TEMP_25[18] == 0x00
    assert TEMP_25[19] == 0x33  # 25 C
    # Envelope bytes are zero on temp-only frames
    for idx in (31, 32, 33, 34, 35):
        assert TEMP_25[idx] == 0x00


# ---------------------------------------------------------------------------
# High-nibble mode mapping (must match what AC reports back in status)
# ---------------------------------------------------------------------------

def test_command_mode_high_nibble_table():
    """The high nibble of status[18] selects the mode.

    These nibble IDs match the mode IDs the AC reports back via
    ``payload[16] >> 4`` in its status responses (FAN=0, HEAT=1, COOL=2,
    DRY=3, AUTO=4..7, OFF=12). The historical command frames use the
    odd-numbered set (FAN=1, HEAT=3, COOL=5, DRY=7) which corresponds to
    ``(report_id << 1) | 1`` -- a separate command-side encoding.
    """
    assert (MODE_FAN[18] >> 4) == 0x1
    assert (MODE_HEAT[18] >> 4) == 0x3
    assert (MODE_COOL[18] >> 4) == 0x5
    assert (MODE_DRY[18] >> 4) == 0x7
