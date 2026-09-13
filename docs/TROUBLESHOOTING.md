# Troubleshooting

## Symptom: Home Assistant entity never initialises

> **Note:** This bug was fixed in the streaming-parser rewrite of
> `parse_ac_message_byte_()` / `try_extract_frame_()`. The notes below remain
> for historical context and as a debugging guide if the symptom returns.

The most common pre-fix symptom: the device boots, connects to Wi-Fi, but the
climate card in Home Assistant stays "Unknown" forever. The logs show a
continuous loop of:

```
Requesting status
Wrong magic start sequence 0x… 0x…
Parse error (consecutive: N)
Communication timeout - resetting
Retrying communication
```

**Root cause.** The original C++ parser was not resync-safe. When a single
stray byte arrived before a real frame — which happens routinely with this
hardware — the parser flagged PARSE_ERROR, cleared the entire receive buffer,
and went back to standby. The next status response then arrived while the
buffer was still being torn down, its leading `F4 F5` header was lost, and
the cycle repeated forever.

**The fix.** `try_extract_frame_()` in `air_conditioner.cpp` now mirrors the
pure-Python `StreamingParser` in `tests/protocol.py`: garbage bytes before
the next valid `F4 F5` header are silently discarded; closed-but-invalid
frames are rescanned for an embedded real header; the rx buffer is never
wholesale cleared. The `tests/test_streaming_parser.py` suite replays the
exact byte sequence from `output.txt` and asserts that real frames buried
between garbage are still recognised.

## Symptom: continuous checksum errors

```
Checksum error #N - expected: 0xHH 0xHH, got: 0xHH 0xHH
```

The Hisense indoor MCU is known to corrupt frames at the physical layer. Two
distinct corruption modes have been seen in real captures:

1. **Single byte dropped** — the computed checksum is off by exactly the value
   of the missing byte (typical: 0x80 difference). This is caused by the ESP
   side missing a UART byte, almost always because some other ESPHome
   component (e.g. `uart.debug` or a verbose logger) is blocking the loop for
   longer than ~1 ms while bytes are still arriving at 9600 baud. The fix is
   to disable `uart.debug` in production and keep the logger at `INFO`. The
   committed `sampleconfig.yaml` already does both.

2. **Doubled `0xF4` before footer** — the frame ends `… cs_hi cs_lo F4 F4 FB`
   (one byte longer than nominal) and the parser sees `F4 F4` as the checksum
   bytes. The C++ extractor and the Python `parse_frame_lenient` helper now
   recover from this automatically by dropping one of the doubled F4s and
   revalidating. The original captured frame fixture is preserved at
   `tests/data/frames.json -> doubled_f4_corruption` with the corresponding
   regression test.

Verify the algorithm itself is correct:

```bash
make test
```

If `test_checksum.py` and `test_frame_parsing.py` are green, the algorithm is
right and any remaining failures are on-wire corruption that the resync-safe
parser will recover from on the next clean frame.

## Symptom: long stretches of "Communication timeout"

If the AC is OFF the indoor MCU sometimes ignores queries for several seconds.
The defaults err on the patient side:

- `QUERY_PERIOD_MS = 5000` — one query every 5 s.
- `COMM_TIMEOUT_MS = 5000` — give up on an in-flight query after 5 s.
- Backoff escalates `2 → 4 → 7 → 10` seconds with consecutive failures.

These are constants in `hisense/air_conditioner.h` if you
need to tune them for a different unit.

## Symptom: sensors stuck at 0

The sub-sensors only update inside `decode_message()`, which only runs after a
successful parse. If the parser never finishes a frame, **every** sub-sensor
is stuck. Fix the parser first — see the first symptom above.

## ESP-01 specifics

- GPIO1 and GPIO3 are the only available UART pins, so serial logging is
  disabled (`logger: baud_rate: 0`) and all logs go over Wi-Fi.
- `rx_buffer_size: 512` is required to fit a full 82-byte response plus
  surrounding noise without overflowing the ESPHome UART software buffer.
  The hardware FIFO on ESP8266 is only ~128 B, so any blocking loop
  iteration over a few ms will drop bytes regardless of the SW buffer size.
- The ESP-01 is slow; bytes often arrive one at a time. The pure-Python
  `StreamingParser` tests with a byte-at-a-time feed to mirror this.

## Reading the wire

The sample config ships with `uart.debug` **commented out** because logging
every frame synchronously through ESPHome's logger is a leading cause of byte
drops on ESP8266. For one-shot debugging you can re-enable it: uncomment the
`debug:` block in `sampleconfig.yaml` and reflash. Lines beginning with `<<<`
are RX (AC → ESP); lines beginning with `>>>` are TX (ESP → AC). A clean
status response should look like:

```
<<< F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 00 00 30 15 17 15 80 80
    00 01 01 00 00 00 … 04 C3 F4 FB
```

If the leading `F4 F5` is missing or the line ends without `F4 FB`, the
parser will reject the frame. Disable `uart.debug` again once you are done
investigating — leaving it on in production causes the very corruption you
were trying to debug.
