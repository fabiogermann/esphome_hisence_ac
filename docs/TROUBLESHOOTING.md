# Troubleshooting

## Symptom: Home Assistant entity never initialises

The most common symptom: the device boots, connects to Wi-Fi, but the climate
card in Home Assistant stays "Unknown" forever. The logs show a continuous
loop of:

```
Requesting status
Wrong magic start sequence 0x… 0x…
Parse error (consecutive: N)
Communication timeout - resetting
Retrying communication
```

**Root cause.** The C++ parser in `AirConditioner::parse_ac_message_byte_()`
is not resync-safe. When a single stray byte arrives before the real frame —
which happens routinely with this hardware — the parser flags PARSE_ERROR,
clears the entire receive buffer, and goes back to standby. The next status
response then arrives while the buffer is still being torn down, its leading
`F4 F5` header is lost, and the cycle repeats forever.

**Confirming the bug locally.** The `tests/test_streaming_parser.py` suite
replays the byte sequence from `output.txt` and asserts that the real frames
buried between garbage bytes are recognised. The pure-Python `StreamingParser`
in `tests/protocol.py` is the executable specification — bring the C++ parser
into line with it and HA initialises correctly.

**Workaround until fixed:** restart the firmware repeatedly until a clean
`F4 F5 …` happens to arrive as the very first bytes on the UART. There is no
firmware-side knob for this.

## Symptom: continuous checksum errors

```
Checksum error #N - expected: 0xHH 0xHH, got: 0xHH 0xHH
```

Verify the wiring: TX↔RX must be crossed (AC pin 2 → ESP RX, AC pin 3 → ESP
TX). Use the test suite to confirm the checksum algorithm itself is correct:

```bash
make test
```

If `test_checksum.py` is green, the algorithm is right and the on-wire bytes
are being corrupted somewhere between the AC and the ESP.

## Symptom: sensors stuck at 0

The sub-sensors only update inside `decode_message()`, which only runs after a
successful parse. If the parser never finishes a frame, **every** sub-sensor
is stuck. Fix the parser first — see the first symptom above.

## ESP-01 specifics

- GPIO1 and GPIO3 are the only available UART pins, so serial logging is
  disabled (`logger: baud_rate: 0`) and all logs go over Wi-Fi.
- `rx_buffer_size: 256` is required to fit a full 82-byte response plus
  surrounding noise without overflowing.
- The ESP-01 is slow; bytes often arrive one at a time. The pure-Python
  `StreamingParser` tests with a byte-at-a-time feed to mirror this.

## Reading the wire

The sample config enables uart_debug with `delimiter: [0xF4, 0xFB]`, which
splits each log line at the trailing footer. Lines beginning with `<<<` are
RX (AC → ESP); lines beginning with `>>>` are TX (ESP → AC). A clean status
response should look like:

```
<<< F4 F5 01 40 49 01 00 FE 01 01 01 01 00 66 00 01 00 00 30 15 17 15 80 80
    00 01 01 00 00 00 … 04 C3 F4 FB
```

If the leading `F4 F5` is missing or the line ends without `F4 FB`, the
parser will reject the frame.
