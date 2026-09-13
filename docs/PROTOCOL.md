# Protocol reference

UART protocol used by Hisense AEH-W4A1 / AEH-W4B1 Wi-Fi modules.

- **Baud rate:** 9600 8N1
- **Endianness:** big-endian (most-significant byte first)
- **Reference implementation:** [`hisense/air_conditioner.cpp`](../hisense/air_conditioner.cpp)
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

**TX byte-stuffing.** Any literal `0xF4` inside the body or the two checksum
bytes is transmitted twice (`F4 F4`); header `F4 F5` and footer `F4 FB` are
sent literal. The AC de-stuffs on receive. Without stuffing, frames whose
body/checksum contain `0xF4` (e.g. a 16 °C setpoint → checksum low byte
`0xF4`) collide with the `F4 FB` footer marker. Adopted from the upstream
(pslawinski) on-wire templates, which pre-stuff — e.g. `temp_16_C` ends
`... 01 F4 F4 F4 FB`.

**RX de-stuffing (two-pass).** Some units double literal `0xF4` on
*transmit* as well (upstream pslawinski `8eb76f2` / `e5a3ee3`). The embedded
checksum is then computed over the **de-stuffed** body. The extractor
therefore validates each candidate frame twice: first the raw bytes (units
that don't stuff — behaviour identical to before), and only on checksum
failure after collapsing every `F4 F4` pair between header and footer.
This is backwards compatible: frames that validated before validate
identically on pass 1; pass 2 only rescues frames that would previously
have been dropped as checksum errors.

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

**Fahrenheit variant.** US-market AEH-W4A1 units (upstream PR #11) carry
Fahrenheit raw values in `body[17]`/`body[18]` (target + indoor temp) and in
all temperature sensor offsets (`body[42..45]`). ESPHome Home-Assistant
integration always works in °C, so when `use_fahrenheit: true` is set the
component converts °F→°C on decode and °C→°F on every command. Default is
Celsius.

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

Command frames are 50 bytes long. **Mode and power are packed into a single
byte** `body[16]`; there is no separate "envelope" or command discriminator.
Body offsets that vary by command:

| Body offset | Purpose | Power-on mode frame | Temp-only frame | OFF frame |
|-------------|---------|---------------------|-----------------|-----------|
| `body[14]`  | (unused, `0x00`) | `0x00` | `0x00` | `0x00` |
| `body[15]`  | (unused, `0x00`) | `0x00` | `0x00` | `0x00` |
| `body[16]`  | **mode + power** (see table below) | `((m<<1)\|1)<<4 \| 0x0C` | `0x00` | `0x04` |
| `body[17]`  | target temperature `((C<<1)|1)` | set | set | `0x00` |
| `body[21]`  | fixed flag | `0x04` | `0x04` | `0x04` |
| `body[30]`  | swing override (optional) | set / `0x00` | `0x00` | `0x00` |
| `body[34]`  | display LED (`0xC0` on, `0x40` off) | set | set | set |

> Note: in the C++ source the buffer variable `status[i]` includes the
> `F4 F5` header at indices 0 and 1, so `status[16]` in the code is
> `body[14]` here, and `status[18]` (the mode byte) is `body[16]`.
> `tests/test_command_frames.py` uses the same `status[i]` (with header)
> indexing and pins the canonical reference frames.

The command-side mode byte `body[16]` packs the mode in the **high nibble**
and the power-on bits `0x0C` in the **low nibble**:

    body[16] = ((encode_mode << 1) | 1) << 4 | 0x0C   # power on
    body[16] = 0x04                                     # OFF sentinel
    body[16] = 0x00                                     # temp-only (no mode)

| HA mode  | encode_mode | Command `body[16]` (power on) |
|----------|-------------|-------------------------------|
| FAN_ONLY | 0           | `0x1C` |
| HEAT     | 1           | `0x3C` |
| COOL     | 2           | `0x5C` |
| DRY      | 3           | `0x7C` |
| AUTO     | 4           | `0x9C` |
| OFF      | —           | `0x04` (sentinel) |

The high nibble is the command-side encoding `(report_id << 1) | 1`, distinct
from the response-side mode IDs the AC reports back (FAN=0, HEAT=1, COOL=2,
DRY=3, AUTO=4..7, OFF=12). The low nibble `0x0C` (bits 2+3) is what asserts
power-on; without it the AC shifts its mode register but never starts the
compressor.

> **History / regression note.** An earlier rewrite (commit c1609e9) replaced
> this single-byte encoding with `body[14]=0x01`, `body[15]=0x01`,
> `body[16]=mode<<4` (e.g. COOL `0x50`) plus a `body[29..33]=10 01 04 00 10`
> "envelope", reverse-engineered from the historical *mode-change-while-on*
> frames in `hisense_ac.h`. That frame is accepted by the AC (one beep) but
> **never asserts the power bit**, so power-on from Home Assistant stopped
> working — the unit stayed OFF (status response `body[16]` with bit `0x08`
> clear). The single-byte `0x?C` encoding above is what actually powers the
> unit on from standby. See `tests/test_command_frames.py` for the canonical
> reference frames and the regression guard.
