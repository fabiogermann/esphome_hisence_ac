# esphome_hisense_ac

ESPHome external component for controlling Hisense air conditioners that use
the proprietary `F4 F5 ... F4 FB` UART protocol (e.g. the AEH-W4A1 / AEH-W4B1
Wi-Fi modules).

> **Status:** the protocol decoder works, but the receive parser is not
> resync-safe — see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the
> known Home-Assistant initialisation bug and the corresponding test suite
> under `tests/`.

## Hardware

I'm using an ESP-8266 NodeMCU (or ESP-01) wired directly to the AC's onboard
Wi-Fi-module connector.

![AC connector pinout](AC%20connector.jpg)

| Pin | Function          |
|-----|-------------------|
| 1   | VCC (5 V from AC) |
| 2   | RX → ESP TX       |
| 3   | TX → ESP RX       |
| 4   | GND               |

Logging is over Wi-Fi only (`logger: baud_rate: 0`) because GPIO1/GPIO3 are
reused for the AC UART on the ESP-01.

## Quickstart

1. Copy the component into your ESPHome `external_components` path:

   ```yaml
   external_components:
     - source:
         type: local
         path: components
       components: [hisense]
   ```

2. Use [`esphome/sampleconfig.yaml`](esphome/sampleconfig.yaml) as a starting
   point. Adjust Wi-Fi credentials, API key, and OTA password.

3. Flash and watch the Wi-Fi logs:

   ```
   esphome run esphome/sampleconfig.yaml
   ```

## Development

A pytest suite covers the protocol layer (checksum, frame parse / build,
encoding, climate-state decoding, streaming-parser behaviour) so the firmware
bugs can be fixed without flashing hardware.

```bash
make venv         # create .venv with pytest + esphome
make test         # run the test suite
make config       # validate esphome/sampleconfig.yaml
make compile      # full firmware build (no upload)
make help         # list every target
```

The `output.txt` file in this repo is a live capture from a Hisense unit and
is referenced by the tests as the source of truth for what the firmware sees
on the wire.

## Documentation

- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) — wire format, byte layout, encoding
  tables.
- [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) — known bugs and
  troubleshooting steps.

## Credits

Prior art that made this possible:

- <https://community.home-assistant.io/t/working-on-integration-for-hisense-aeh-w4a1-module/146243>
- <https://github.com/deiger/AirCon/>
- <https://github.com/simoneluconi/hisense-aeh-w4a1>
- <https://github.com/pslawinski/esphome_airconintl>
