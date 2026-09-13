# Test suite

Pure-Python tests for the Hisense AC UART protocol. They mirror the algorithm
in `component/air_conditioner.cpp` and run in milliseconds —
no hardware, no ESPHome runtime required.

## Layout

| File | Purpose |
|------|---------|
| `protocol.py`              | Pure-Python port of the protocol — checksum, frame build/parse, streaming parser, mode/temp/swing/fan codecs, climate-state decoder. |
| `conftest.py`              | Shared pytest fixtures (loads `data/frames.json`). |
| `data/frames.json`         | Real captured frames + bug cases (truncated frames, headerless garbage). Each frame's `expected_checksum` was verified against the device. |
| `test_checksum.py`         | The 16-bit checksum algorithm — round-trip, endianness, mutation, 16-bit wrap. |
| `test_frame_parsing.py`    | `parse_frame()` accept/reject behaviour. |
| `test_encoding.py`         | Mode / temp / swing / fan-speed encode-decode round-trips. |
| `test_climate_state.py`    | Decoded climate state from real captured frames — what Home Assistant *should* see. |
| `test_streaming_parser.py` | Resync-safe streaming parser — the **HA-init bug** lives here. |
| `test_config.py`           | Compile-only validation of `docs/sampleconfig.yaml` (skipped if the `esphome` CLI isn't installed). |

## Running

```bash
make venv     # install pytest + esphome into .venv (one time)
make test     # run all tests
make test-verbose
```

Or directly:

```bash
python3 -m venv .venv
.venv/bin/pip install pytest
.venv/bin/pytest -q
```

## What's covered

- **Checksum algorithm** — every frame in `data/frames.json` round-trips.
- **Frame parsing** — header, footer, length, checksum failures all surface as
  `FrameError`. Truncated bug case from the live log is rejected cleanly.
- **Encoding** — mode/temp/swing/fan bit-patterns match the firmware.
- **Climate-state decoding** — `decode_status_payload()` extracts everything
  HA needs from a real status response.
- **Streaming parser** — the parser MUST resync after garbage. Several tests
  replay the exact byte sequence from `output.txt` and assert that real
  frames embedded between truncated fragments are still recognised. The C++
  parser in `air_conditioner.cpp` follows the same algorithm.
