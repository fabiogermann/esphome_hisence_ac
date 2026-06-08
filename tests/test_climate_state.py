"""Decode real captured frames into the climate state Home Assistant sees.

These tests are the executable definition of what the firmware MUST report to
Home Assistant after a successful status-response parse. The user's primary
bug is that the HA climate entity never finishes initialising; once the
parser actually delivers a frame, these tests assert the state that should
be published.
"""

from __future__ import annotations

import pytest

from tests import protocol


def _payload(case: dict) -> bytes:
    """Strip header / CS / footer to get the body the firmware would decode."""
    raw = bytes.fromhex(case["hex"])
    return raw[2:-4]


def test_decode_temp19_response_yields_expected_state(well_formed_frames):
    case = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )
    state = protocol.decode_status_payload(_payload(case))

    # byte[16] == 0x30 → power bit (0x08) not set → AC reports OFF
    assert state.power_on is False
    assert state.mode == protocol.MODE_OFF

    # byte[17] == 0x15 == 21 → target 21 °C
    assert state.target_temp_c == 21

    # byte[18] == 0x17 == 23 → indoor 23 °C
    assert state.indoor_temp_c == 23

    # byte[33] == 0x00 → swing off
    assert state.swing_mode == "off"


def test_decode_temp20_response_differs_only_in_one_byte(well_formed_frames):
    case_a = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )
    case_b = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp20"
    )
    state_a = protocol.decode_status_payload(_payload(case_a))
    state_b = protocol.decode_status_payload(_payload(case_b))

    # The two captures differ by one byte, but it's NOT the target-temp byte;
    # what HA sees as target should be the same.
    assert state_a.target_temp_c == state_b.target_temp_c == 21
    assert state_a.mode == state_b.mode == protocol.MODE_OFF


def test_decode_publishes_all_sub_sensors(well_formed_frames):
    """A successful decode must populate every sub-sensor the firmware exports."""
    case = next(
        f for f in well_formed_frames if f["name"] == "status_response_temp19"
    )
    state = protocol.decode_status_payload(_payload(case))

    # Every numeric attribute the C++ update_sub_sensor_ writes should be set.
    for field_name in (
        "indoor_temp_c",
        "indoor_coil_temp_c",
        "indoor_humidity",
        "outdoor_temp_c",
        "outdoor_coil_temp_c",
    ):
        assert hasattr(state, field_name), field_name
        # All values are bytes so 0..255 - just confirm they're integers.
        assert isinstance(getattr(state, field_name), int)


def test_decode_rejects_short_payload():
    with pytest.raises(protocol.FrameError, match="too short"):
        protocol.decode_status_payload(b"\x00" * 30)


def test_real_response_temperature_in_visual_range(well_formed_frames):
    """The target temperature in real captures must fall in HA's visual range.

    If the firmware advertises 16..30 °C to HA but the captured target is
    outside that range, HA refuses to render the slider and the entity stays
    "unknown" - one of the symptoms of the init bug.
    """
    for case in well_formed_frames:
        if not case["name"].startswith("status_response"):
            continue
        state = protocol.decode_status_payload(_payload(case))
        assert protocol.is_temp_in_range(state.target_temp_c), (
            f"{case['name']}: target {state.target_temp_c} °C outside 16..30"
        )
