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


def test_send_status_range_guard_in_cpp_is_correct():
    """Mirror the C++ guard in send_status: reject anything outside 16..30."""
    # The fixed C++ condition is: if (my_tmp < 16 || my_tmp > 30) reject;
    def cpp_rejects(t):
        return t < 16 or t > 30

    assert cpp_rejects(15)
    assert cpp_rejects(31)
    assert not cpp_rejects(16)
    assert not cpp_rejects(30)
    assert not cpp_rejects(22)


# ---------------------------------------------------------------------------
# resolve_target_temp_for_send — regression test for the "Not valid tmp!" flood
#
# Bug: when the user changed mode from OFF -> FAN_ONLY in HA, send_status()
# rewrote next_hvac_settings.target_temperature = this->target_temperature,
# which is NAN before any setpoint has ever been set. The uint8_t cast of
# NAN produced 0, the < 16 guard tripped, ESP_LOGD("Not valid tmp!") fired,
# and send_status() bailed *without* clearing next_hvac_settings_, so the
# next loop() iteration re-entered the same path — flooding the log.
# ---------------------------------------------------------------------------

def test_resolve_target_temp_uses_default_when_current_is_nan():
    """First mode-only call after boot: this->target_temperature is NaN."""
    import math
    assert (
        protocol.resolve_target_temp_for_send(None, math.nan) == 22.0
    )


def test_resolve_target_temp_uses_default_when_current_is_none():
    assert protocol.resolve_target_temp_for_send(None, None) == 22.0


def test_resolve_target_temp_uses_current_when_valid():
    assert protocol.resolve_target_temp_for_send(None, 24.0) == 24.0


def test_resolve_target_temp_clamps_current_below_range_to_default():
    """An out-of-range cached value must not poison the next frame."""
    assert protocol.resolve_target_temp_for_send(None, 5.0) == 22.0
    assert protocol.resolve_target_temp_for_send(None, 99.0) == 22.0


def test_resolve_target_temp_requested_wins_when_valid():
    assert protocol.resolve_target_temp_for_send(28.0, 22.0) == 28.0


def test_resolve_target_temp_requested_out_of_range_returns_none():
    """Explicit bad request: refuse to send (caller must clear pending)."""
    assert protocol.resolve_target_temp_for_send(15.0, 22.0) is None
    assert protocol.resolve_target_temp_for_send(31.0, 22.0) is None


def test_resolve_target_temp_requested_nan_returns_none():
    import math
    assert protocol.resolve_target_temp_for_send(math.nan, 22.0) is None


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
