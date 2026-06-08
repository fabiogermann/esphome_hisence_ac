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
| `body[21]`  | Static flag byte (always observed as `0x80` — **not** humidity) |
| `body[33]`  | Swing bits — see [Swing](#swing) |
| `body[42]`  | Outdoor air temperature, °C |
| `body[43]`  | Outdoor coil temperature, °C |
| `body[44]`  | Outdoor defrost / sub-coil temperature, °C (not exposed) |
| `body[45]`  | Compressor / heatsink temperature, °C (not exposed) |

> **Note on humidity.** The original community implementations read
> `body[21]` as an indoor humidity percentage. On every observed Hisense
> status frame from real hardware that byte is a static `0x80` (= 128 in
> decimal — the cause of the long-standing "Indoor Humidity 128 %" bug).
> This driver therefore does **not** expose an indoor humidity sensor.
>
> **Note on outdoor temperatures.** Earlier versions read
> `body[40]` / `body[41]`, but on real captures those bytes are always
> `0x00` (hence "Outdoor Temperature 0 °C" in HA). The actual outdoor
> sensor block lives at `body[42..45]`.

## Mode byte (status response)

`body[16]` of a status response packs both the climate mode and the power
state.

- **Bit 3** (`0x08`): power on (1) or off (0).
- **High nibble** (`body[16] >> 4`): mode code from the table below.
  *(Despite the firmware-side command encoding looking like
  `((mode << 1) | 1)`, the AC reports the plain mode code in its
  responses — i.e. the response high-nibble for COOL is `0x2`, for HEAT
  `0x1`, etc. See [Command frames](#command-frames-esp--ac) for the
  separate command-side encoding.)*

| Mode code | HA mode  |
|-----------|----------|
| 0         | FAN_ONLY |
| 1         | HEAT     |
| 2         | COOL     |
| 3         | DRY     |
| 4–7       | AUTO     |
| 12        | OFF      |

Worked example: a status frame with `body[16] = 0x28`:

```
power_on = (0x28 & 0x08) != 0      = true
mode_id  = (0x28 >> 4)              = 0x2 -> COOL
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

## Command frames (ESP → AC)

Command frames are 50 bytes long and have a fixed envelope. Body offsets
that vary by command are summarised below; everything else stays zero.

| Body offset | Purpose | Mode-change frame | Temp-only frame | OFF frame |
|-------------|---------|-------------------|-----------------|-----------|
| `body[14]`  | sub-command selector | `0x01` (cool/heat/dry/auto) or `0x07` (fan-only) | `0x00` | `0x00` |
| `body[15]`  | "active" flag | `0x01` | `0x00` | `0x01` |
| `body[16]`  | mode byte (see table below) | mode nibble << 4 | `0x00` | `0x04` |
| `body[17]`  | target temperature `((C<<1)|1)` | set | set | `0x00` |
| `body[29]`  | envelope | `0x10` | `0x00` | `0x00` |
| `body[30]`  | envelope (or swing override) | `0x01` | `0x00` | `0x01` |
| `body[31]`  | envelope | `0x04` | `0x00` | `0x55` |
| `body[32]`  | envelope | `0x00` | `0x00` | `0x00` |
| `body[33]`  | envelope | `0x10` | `0x00` | `0x01` |
| `body[34]`  | display LED (`0xC0` on, `0x40` off) | set | set | set |

> Note: in the C++ source the buffer variable `status[i]` includes the
> `F4 F5` header at indices 0 and 1, so `status[16]` in the code is
> `body[14]` here. The Python reference in
> `tests/test_command_frames.py` uses the same `status[i]` (with header)
> indexing.

The command-side mode nibble in `body[16]` follows a different convention
from the response-side `body[16] >> 4`:

| HA mode  | Response high nibble | Command `body[16]` |
|----------|----------------------|--------------------|
| FAN_ONLY | 0                    | `0x10` |
| HEAT     | 1                    | `0x30` |
| COOL     | 2                    | `0x50` |
| DRY      | 3                    | `0x70` |
| AUTO     | 4–7                  | `0x90` |
| OFF      | 12                   | `0x04` (sentinel) |

> **Why the asymmetry?** The historical community implementation captured
> on-the-wire command frames per mode. Those captures show the AC accepts
> only this exact envelope; in particular **omitting `body[14]=0x01` and
> the `body[29..33]` envelope makes the AC silently ignore the command**
> — even though such a "minimal" frame still checksums correctly. This
> was the cause of the "switching from FAN_ONLY to COOL does nothing"
> bug. The driver therefore reconstructs the full historical envelope in
> `send_status`. See `tests/test_command_frames.py` for the canonical
> reference frames.
