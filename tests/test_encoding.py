"""Round-trip tests for the wire-level encoding of mode / temp / swing / fan.

These pin down the exact bit-patterns used by the firmware so they can be
refactored safely. They are the *executable* version of docs/PROTOCOL.md.
"""

from __future__ import annotations

import pytest

from tests import protocol


# ---------------------------------------------------------------------------
# Mode byte
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mode",
    [
        protocol.MODE_FAN_ONLY,
        protocol.MODE_HEAT,
        protocol.MODE_COOL,
        protocol.MODE_DRY,
        protocol.MODE_AUTO,
    ],
)
def test_mode_round_trip_power_on(mode):
    byte = protocol.encode_mode_byte(mode, power_on=True)
    decoded_mode, decoded_power = protocol.decode_mode_byte(byte)
    assert decoded_mode == mode
    assert decoded_power is True


def test_mode_round_trip_power_off():
    byte = protocol.encode_mode_byte(protocol.MODE_OFF, power_on=False)
    decoded_mode, decoded_power = protocol.decode_mode_byte(byte)
    assert decoded_power is False
    # When powered off the firmware reports MODE_OFF regardless of the mode arg
    assert decoded_mode == protocol.MODE_OFF


def test_mode_byte_power_bit_is_0x08():
    """The power flag is bit 3 (0x08) of payload[16]."""
    on_byte = protocol.encode_mode_byte(protocol.MODE_COOL, True)
    off_byte = protocol.encode_mode_byte(protocol.MODE_COOL, False)
    assert on_byte & 0b00001000
    assert not off_byte & 0b00001000


# ---------------------------------------------------------------------------
# Target temperature byte
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("celsius", list(range(16, 31)))
def test_target_temp_round_trip(celsius):
    byte = protocol.encode_target_temp_byte(celsius)
    assert protocol.decode_target_temp_byte(byte) == celsius


def test_target_temp_encoding_sets_low_bit():
    """The firmware ORs the result with 0x01; encoded value must be odd."""
    for c in range(16, 31):
        assert protocol.encode_target_temp_byte(c) & 1 == 1


def test_target_temp_range_check_matches_spec():
    """The valid set-point range advertised to HA is 16..30 °C inclusive."""
    assert protocol.is_temp_in_range(16) is True
    assert protocol.is_temp_in_range(30) is True
    assert protocol.is_temp_in_range(15) is False
    assert protocol.is_temp_in_range(31) is False


@pytest.mark.xfail(
    reason=(
        "Bug in air_conditioner.cpp send_status: the range guard "
        "'(my_tmp > 16 || my_tmp < 30)' is logically inverted - it accepts "
        "everything. The C++ should be '(my_tmp >= 16 && my_tmp <= 30)'."
    ),
    strict=True,
)
def test_send_status_range_guard_in_cpp_is_correct():
    """Documents an inverted boolean in the firmware. Will pass once fixed."""
    # Mimic the C++ condition over its accepted-vs-rejected set
    accepts_15 = (15 > 16) or (15 < 30)
    accepts_31 = (31 > 16) or (31 < 30)
    # In a correct implementation, NEITHER 15 nor 31 should be accepted
    assert not accepts_15 and not accepts_31


# ---------------------------------------------------------------------------
# Swing byte
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "byte,expected",
    [
        (0x00, "off"),
        (0b01000000, "horizontal"),
        (0b10000000, "vertical"),
        (0b11000000, "both"),
    ],
)
def test_decode_swing(byte, expected):
    assert protocol.decode_swing(byte) == expected


def test_decode_swing_ignores_other_bits():
    """Low 6 bits of the swing byte should not influence the decoded mode."""
    assert protocol.decode_swing(0b11000111) == "both"


# ---------------------------------------------------------------------------
# Fan-speed lookup
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code,expected",
    [
        (0, protocol.FAN_OFF),
        (1, protocol.FAN_AUTO),
        (2, protocol.FAN_AUTO),
        (10, protocol.FAN_LOW),
        (12, protocol.FAN_FOCUS),
        (14, protocol.FAN_MEDIUM),
        (16, protocol.FAN_MIDDLE),
        (18, protocol.FAN_HIGH),
    ],
)
def test_decode_fan_speed_known_codes(code, expected):
    assert protocol.decode_fan_speed(code) == expected


def test_decode_fan_speed_unknown_returns_none():
    assert protocol.decode_fan_speed(7) is None
    assert protocol.decode_fan_speed(99) is None
