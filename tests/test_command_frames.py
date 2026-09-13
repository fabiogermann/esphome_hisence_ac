"""Pin the command-frame format the firmware sends to the AC.

Mode and power are packed into the SINGLE byte ``status[18]``; there is no
command discriminator and no status[31..35] envelope. The encoding (see
``component/air_conditioner.cpp::send_status``):

    power-on + mode : ((encode_mode << 1) | 1) << 4 | 0x0C
    OFF              : 0x04
    temp-only        : mode byte untouched (0x00)

with encode_mode FAN=0, HEAT=1, COOL=2, DRY=3, AUTO=4. The low nibble 0x0C
(bits 2+3) asserts power; without it the AC shifts its mode register but
never starts the compressor.

REGRESSION: commit c1609e9 had reverted to the historical
"mode-change-while-on" envelope frames (status[16]=0x01, status[17]=0x01,
status[31..35]=10 01 04 00 10) which ACK with a single beep but never
assert the power bit. The power-on frames below were verified on real
hardware (see debug_poweron_button.yaml / docs/PROTOCOL.md).
"""

from __future__ import annotations

from tests import protocol

# 46-byte template copied from send_status() in air_conditioner.cpp.
# 46 bytes total: header(2) + body(42) + fixed flag byte at [23].
BASE_STATUS = bytes([
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE,
    0x01, 0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
])
assert len(BASE_STATUS) == 46

DISPLAY_ON = 0xC0
DISPLAY_OFF = 0x40


def build_status_frame(
    mode: int | None = None,
    temp_c: int | None = None,
    display: int = DISPLAY_ON,
) -> bytes:
    """Build a send_status command frame the way the C++ does."""
    body = bytearray(BASE_STATUS)
    if mode is not None and mode != protocol.MODE_OFF:
        body[18] = protocol.encode_mode_byte(mode, power_on=True)
    elif mode == protocol.MODE_OFF:
        body[18] = 0x04  # OFF sentinel
    if temp_c is not None:
        body[19] = protocol.encode_target_temp_byte(temp_c)
    body[36] = display
    return protocol.build_frame(bytes(body))


# ---------------------------------------------------------------------------
# Power-on frames (hardware-verified encoding)
# ---------------------------------------------------------------------------

def test_poweron_cool_frame():
    frame = build_status_frame(mode=protocol.MODE_COOL, temp_c=21)
    assert frame[18] == 0x5C
    assert (frame[19] >> 1) == 21
    assert frame[36] == DISPLAY_ON
    protocol.parse_frame(frame)  # checksum must validate


def test_poweron_heat_frame():
    frame = build_status_frame(mode=protocol.MODE_HEAT, temp_c=22)
    assert frame[18] == 0x3C
    assert (frame[19] >> 1) == 22
    protocol.parse_frame(frame)


def test_poweron_fan_frame():
    frame = build_status_frame(mode=protocol.MODE_FAN_ONLY, temp_c=25)
    assert frame[18] == 0x1C
    protocol.parse_frame(frame)


def test_poweron_dry_frame():
    frame = build_status_frame(mode=protocol.MODE_DRY, temp_c=25)
    assert frame[18] == 0x7C
    protocol.parse_frame(frame)


def test_poweron_auto_frame():
    frame = build_status_frame(mode=protocol.MODE_AUTO, temp_c=25)
    assert frame[18] == 0x9C
    protocol.parse_frame(frame)


def test_poweroff_sentinel():
    frame = build_status_frame(mode=protocol.MODE_OFF)
    assert frame[18] == 0x04
    # Everything from status[31] on stays zero - no envelope.
    for idx in range(31, 36):
        assert frame[idx] == 0x00
    protocol.parse_frame(frame)


def test_temp_only_leaves_mode_byte_alone():
    frame = build_status_frame(temp_c=25)
    assert frame[16] == 0x00
    assert frame[17] == 0x00
    assert frame[18] == 0x00
    assert (frame[19] >> 1) == 25
    protocol.parse_frame(frame)


def test_three_frame_checksums_match_proven_hardware_values():
    """Checksums proven on hardware via debug_poweron_button.yaml."""
    cool = build_status_frame(mode=protocol.MODE_COOL, temp_c=21)
    heat = build_status_frame(mode=protocol.MODE_HEAT, temp_c=22)
    off = build_status_frame(mode=protocol.MODE_OFF)
    assert cool[-4:-2] == bytes([0x03, 0x1A])
    assert heat[-4:-2] == bytes([0x02, 0xFC])
    assert off[-4:-2] == bytes([0x02, 0x97])


# ---------------------------------------------------------------------------
# Regression guards: the old envelope frames must NOT be emitted
# ---------------------------------------------------------------------------

def test_no_legacy_envelope_bytes():
    """c1609e9 regression: envelope frames ACK but never power on."""
    for mode in (
        protocol.MODE_FAN_ONLY,
        protocol.MODE_HEAT,
        protocol.MODE_COOL,
        protocol.MODE_DRY,
        protocol.MODE_AUTO,
        protocol.MODE_OFF,
    ):
        frame = build_status_frame(mode=mode, temp_c=25)
        assert frame[16] != 0x01, "legacy discriminator byte must not be set"
        assert frame[17] != 0x01, "legacy discriminator flag must not be set"
        # The 10 01 04 00 10 envelope lives at status[31..35]
        assert list(frame[31:36]) != [0x10, 0x01, 0x04, 0x00, 0x10]


def test_power_bits_asserted_on_all_modes():
    """Bits 2+3 (0x0C) must be present on every power-on mode byte."""
    for mode, expected in [
        (protocol.MODE_FAN_ONLY, 0x1C),
        (protocol.MODE_HEAT, 0x3C),
        (protocol.MODE_COOL, 0x5C),
        (protocol.MODE_DRY, 0x7C),
        (protocol.MODE_AUTO, 0x9C),
    ]:
        assert protocol.encode_mode_byte(mode, power_on=True) == expected
        assert expected & 0x0C == 0x0C


# ---------------------------------------------------------------------------
# TX byte-stuffing (adopted from upstream templates)
# ---------------------------------------------------------------------------

def _destuff(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i] == 0xF4 and i + 1 < len(data) and data[i + 1] == 0xF4:
            out.append(0xF4)
            i += 2
        else:
            out.append(data[i])
            i += 1
    return bytes(out)


def test_stuff_wire_duplicates_f4():
    data = bytes([0x01, 0xF4, 0x02, 0xF4, 0x03])
    assert protocol.stuff_wire(data) == bytes(
        [0x01, 0xF4, 0xF4, 0x02, 0xF4, 0xF4, 0x03]
    )


def test_stuff_wire_leaves_clean_data_untouched():
    data = bytes([0x01, 0x02, 0x03])
    assert protocol.stuff_wire(data) == data


def test_stuff_destuff_roundtrip():
    """Remote-style math on a 16C setpoint whose checksum low byte is 0xF4
    (upstream temp_16_C template: cs 0x01F4 goes out as 01 F4 F4 F4 FB)."""
    payload = bytearray(BASE_STATUS)
    payload[19] = protocol.encode_target_temp_byte(16)  # 0x21
    cs = protocol.checksum_bytes(bytes(payload))
    wire = protocol.build_wire_frame(bytes(payload))
    assert wire[:2] == protocol.HEADER
    assert wire[-2:] == protocol.FOOTER
    stuffed_mid = wire[2:-2]
    assert _destuff(stuffed_mid) == bytes(payload[2:]) + cs
