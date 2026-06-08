# Modern Hisense AC ESPHome Integration

A modernized ESPHome external component for controlling Hisense air conditioners via UART, compatible with ESPHome 2024.12.x and later versions. This implementation uses ESPHome's external component structure, eliminating custom platform warnings.

## 🌟 Features

This integration combines the best features from multiple community implementations:

### Core Features
- ✅ **External Component Structure** - No more custom platform warnings
- ✅ Full climate control (power, mode, temperature, fan, swing)
- ✅ Real-time status monitoring
- ✅ Bi-directional communication via UART
- ✅ Support for both ESP32 and ESP8266
- ✅ Home Assistant integration with encryption
- ✅ Web interface for local control
- ✅ OTA updates with password protection

### Advanced Features
- 🌡️ Multiple temperature sensors (room, pipe, outdoor, condenser, exhaust)
- 💨 Compressor frequency monitoring
- 🔄 Automatic status synchronization
- 🎯 Special modes: Turbo, ECO, Quiet, Sleep
- 💡 LED display control
- 🔀 Independent horizontal and vertical swing control
- 📊 HVAC action detection (heating, cooling, idle, etc.)

## 📋 Requirements

- ESPHome 2024.12.x or later
- ESP32 or ESP8266 board
- TTL to RS485 converter (if your AC uses RS485)
- Home Assistant (optional but recommended)

## 🔌 Hardware Connection

### ESP32 Wiring
```
ESP32         TTL/RS485 Converter    AC Unit
GPIO17 (TX) → RX                   → AC RX
GPIO16 (RX) → TX                   → AC TX
GND         → GND                  → GND
3.3V/5V     → VCC                  → -
```

### ESP8266 Wiring
```
ESP8266       TTL/RS485 Converter    AC Unit
GPIO1 (TX)  → RX                   → AC RX
GPIO3 (RX)  → TX                   → AC TX
GND         → GND                  → GND
3.3V        → VCC                  → -
```

## 🚀 Installation

### Quick Start

1. **Validate your setup** using our automated script:
   ```bash
   ./validate_config.sh
   ```
   This will check ESPHome installation, required files, and configuration validity.

2. **For detailed testing**, see [TESTING_GUIDE.md](TESTING_GUIDE.md)
3. **Migrating from old config?** See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)

### 1. Prepare Configuration Files

1. Copy the entire `modern_hisense_ac` folder to your ESPHome configuration directory (including the `components` subfolder)
2. Copy `secrets.yaml.example` to `secrets.yaml` and fill in your values:
   ```yaml
   wifi_ssid: "Your_WiFi_SSID"
   wifi_password: "Your_WiFi_Password"
   api_encryption_key: "generate_with_openssl_rand_-base64_32"
   ota_password: "your_ota_password"
   ```

**Important**: The `components/hisense_ac/` folder contains the external component files and must be included.

### 2. Choose Your Board Configuration

We provide pre-configured files for different boards:
- **ESP32**: Use `esp32_variant.yaml`
- **ESP8266**: Use `esp8266_variant.yaml` (memory-optimized)
- **Debug**: Use `debug_config.yaml` (verbose logging)

All configurations now use the external component structure:
```yaml
external_components:
  - source:
      type: local
      path: components
    components: [hisense_ac]

climate:
  - platform: hisense_ac
    name: "Hisense AC"
    uart_id: ac_uart
```

### 3. Compile and Upload

```bash
# First, validate your configuration
./validate_config.sh

# For ESP32
esphome run esp32_variant.yaml

# For ESP8266
esphome run esp8266_variant.yaml

# For debugging issues
esphome run debug_config.yaml
```

### 4. Add to Home Assistant

The device should automatically appear in Home Assistant if auto-discovery is enabled. Otherwise, add it manually through the ESPHome integration.

## 🎮 Usage

### Home Assistant Controls

Once integrated, you'll have access to:

- **Climate Entity**: Full HVAC control with temperature, mode, fan, and swing settings
- **Sensors**: Temperature readings, compressor frequency, humidity
- **Switches**: Power, Turbo, ECO, Quiet, LED, Swing controls
- **Select Boxes**: Mode, Fan speed, Sleep mode selection
- **Number Input**: Target temperature adjustment

### Web Interface

Access the local web interface at `http://<device-ip>` for direct control without Home Assistant.

## 🔧 Configuration Options

### Temperature Range
```yaml
traits.set_visual_min_temperature(16)  # Minimum 16°C
traits.set_visual_max_temperature(32)  # Maximum 32°C
```

### Update Intervals
```yaml
interval:
  - interval: 2s  # Status query interval
```

### UART Settings
```yaml
uart:
  baud_rate: 9600
  rx_buffer_size: 256
```

### Optional DHT22 Sensor
Uncomment to use an external temperature sensor:
```yaml
- platform: dht
  pin: GPIO13
  model: DHT22
  temperature:
    name: "Room Temperature (DHT22)"
  humidity:
    name: "Room Humidity (DHT22)"
```

## 🐛 Troubleshooting

For comprehensive troubleshooting, see our [TESTING_GUIDE.md](TESTING_GUIDE.md).

### Quick Debug

Use the debug configuration for enhanced logging:
```bash
esphome run debug_config.yaml
```

### Common Issues

#### No Communication
1. Check wiring connections
2. Verify UART pins match your configuration
3. Check baud rate (should be 9600)
4. Use `debug_config.yaml` for verbose logging

#### Incorrect Temperature Readings
- The AC might report temperature in different units
- Check if external DHT22 sensor is needed for accurate room temperature

#### Commands Not Working
1. Ensure proper power supply to ESP and converter
2. Check if RS485 converter is needed (some units use RS485 instead of TTL)
3. Verify the protocol matches your AC model

## 📝 Protocol Details

The integration uses a binary protocol with the following structure:
- Header: `0xF4 0xF5`
- Message type and data
- Checksum (16-bit sum)
- Footer: `0xF4 0xFB`

### Command Types
- `0x65`: Control command
- `0x66`: Status query
- `0x01`: Response

## 🔄 Updates and Improvements

### Key Improvements in This Version

1. **External Component Structure**: Eliminates custom platform warnings in modern ESPHome
2. **Modern ESPHome Compatibility**: Updated for 2024.12.x and later
3. **Enhanced Error Handling**: Better checksum validation and retry logic
4. **Improved State Management**: Proper synchronization between ESP and AC unit
5. **Optimized Communication**: Queue-based command handling with timeouts
6. **Better Sensor Support**: All temperature and status sensors properly configured
7. **Security**: API encryption and password-protected OTA updates

### Migration from Older Versions

For detailed migration instructions, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md).

Quick migration steps:
1. Backup your current configuration
2. Run `./validate_config.sh` to check compatibility
3. Update secrets.yaml with new required fields
4. Test with `debug_config.yaml` for verbose logging
5. Verify all sensors and controls work correctly

## 📖 Documentation

- **[TESTING_GUIDE.md](TESTING_GUIDE.md)** - Comprehensive testing and validation procedures
- **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** - Step-by-step migration from older configurations
- **[validate_config.sh](validate_config.sh)** - Automated configuration validation script
- **[debug_config.yaml](debug_config.yaml)** - Enhanced debug configuration for troubleshooting

## 🤝 Contributing

Contributions are welcome! Please:
1. Test changes thoroughly with your AC unit
2. Run `./validate_config.sh` before submitting
3. Include debug logs if reporting issues

## ⚠️ Disclaimer

This integration is provided as-is without warranty. Modifying your AC unit may void its warranty. Use at your own risk.

## 📚 References

Based on work from:
- Original Hisense AC protocol reverse engineering community
- ESPHome climate component documentation
- Various community implementations and improvements

## 📄 License

This project is open source and available under the MIT License.

---

For issues or questions, please check the ESPHome forums or Home Assistant community.