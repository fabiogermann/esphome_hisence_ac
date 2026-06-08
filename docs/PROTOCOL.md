# Protocol reference

UART protocol used by Hisense AEH-W4A1 / AEH-W4B1 Wi-Fi modules.

- **Baud rate:** 9600 8N1
- **Endianness:** big-endian (most-significant byte first)
- **Reference implementation:** [`esphome/components/hisense/air_conditioner.cpp`](../esphome/components/hisense/air_conditioner.cpp)
- **Executable spec:** [`tests/protocol.py`](../tests/protocol.py)

## Frame format

```
+------+------+----------------+--------+--------+------+------+
| 0xF4 | 0xF5 |    payload     | CS_hi  | CS_lo  | 0xF4 | 0xFB |
+------+------+----------------+--------+--------+------+------+
   header        body (n bytes)         checksum    footer
```

**Checksum** = `sum(frame[2:-4]) & 0xFFFF`, i.e. sum every byte between the
header (exclusive) and the CS bytes (exclusive), masked to 16 bits, written
high byte first.

## Message types

The 12th byte of the body (offset 11 into the body, 13 into the full frame)
identifies the message type:

| Code | Meaning   | Direction       |
|------|-----------|-----------------|
| 0x65 | command   | ESP → AC        |
| 0x66 | query     | ESP → AC        |
| 0x01 | response  | AC  → ESP       |

## Status query (ESP → AC)

21-byte fixed frame, sent every ~10 s:

```
F4 F5 00 40 0C 00 00 01 01 FE 01 00 00 66 00 00 00 01 B3 F4 FB
```

## Status response (AC → ESP)

82-byte frame. The body (80 bytes) carries the device state. Byte offsets
below are relative to the body, i.e. `body[0]` is the first byte after `F4 F5`.

| Body offset | Meaning |
|-------------|---------|
| `body[14]`  | Fan-speed code — see [Fan speed](#fan-speed) |
| `body[16]`  | Mode + power — see [Mode byte](#mode-byte) |
| `body[17]`  | Target temperature, °C (raw integer) |
| `body[18]`  | Indoor air temperature, °C |
| `body[19]`  | Indoor coil temperature, °C |
| `body[21]`  | Indoor humidity, % |
| `body[33]`  | Swing bits — see [Swing](#swing) |
| `body[40]`  | Outdoor air temperature, °C |
| `body[41]`  | Outdoor coil temperature, °C |

## Mode byte

`body[16]` packs both the climate mode and the power state.

- **Bit 3** (`0x08`): power on (1) or off (0).
- **High nibble**: `((mode << 1) | 1)` — i.e. an odd value where the low bit
  of the nibble is always 1 and the upper 3 bits encode the mode.

| Mode code | HA mode  |
|-----------|----------|
| 0         | FAN_ONLY |
| 1         | HEAT     |
| 2         | COOL     |
| 3         | DRY      |
| 4–7       | AUTO     |
| 12        | OFF      |

Worked example for COOL, powered on:

```
mode    = 2
nibble  = (2 << 1) | 1 = 5
byte    = (5 << 4) | 0b00001100 = 0x5C
```

## Target temperature byte

Encoded as `((celsius & 0xFF) << 1) | 1` — i.e. doubled and OR'd with 1.
Decode by right-shifting by one. Valid range is 16–30 °C.

## Swing

`body[33]` packs swing into two bits:

| Bit | Meaning      |
|-----|--------------|
| 6 (`0x40`) | Up / down (horizontal louver) |
| 7 (`0x80`) | Left / right (vertical louver) |

| Bit pattern | HA swing mode |
|-------------|---------------|
| `00`        | OFF           |
| `01` (bit 6)| HORIZONTAL    |
| `10` (bit 7)| VERTICAL      |
| `11`        | BOTH          |

(When writing a setpoint, `send_status` instead encodes swing into `body[32]`
using the literals `0x50` OFF / `0x30` VERTICAL / `0x70` HORIZONTAL / `0xF0`
BOTH.)

## Fan speed

`body[14]` is an integer index into the firmware's lookup table:

| Code | Fan mode |
|------|----------|
| 0    | OFF      |
| 1    | AUTO     |
| 2    | AUTO     |
| 10   | LOW      |
| 12   | FOCUS    |
| 14   | MEDIUM   |
| 16   | MIDDLE   |
| 18   | HIGH     |

Codes not in the table are reported as "unknown" by the firmware.
