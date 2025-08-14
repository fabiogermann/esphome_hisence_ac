# Hisense AC ESPHome Testing & Validation Guide

This guide provides comprehensive instructions for testing and validating your Hisense AC ESPHome configuration before and after installation.

## Table of Contents
- [Pre-Installation Checklist](#pre-installation-checklist)
- [Configuration Validation](#configuration-validation)
- [Initial Flash Procedure](#initial-flash-procedure)
- [Component Testing](#component-testing)
- [Home Assistant Integration](#home-assistant-integration)
- [Troubleshooting](#troubleshooting)
- [Debug Logging](#debug-logging)

## Pre-Installation Checklist

### Hardware Requirements
- [ ] ESP32 or ESP8266 development board
- [ ] USB-TTL adapter (if not built into board)
- [ ] 5V power supply (minimum 500mA)
- [ ] Dupont wires for connections
- [ ] Multimeter for voltage verification
- [ ] Logic analyzer (optional, for advanced debugging)

### Wiring Verification
Before connecting to your AC unit:

1. **Power Requirements**
   - Verify your board operates at 3.3V logic level
   - Ensure 5V power supply is stable
   - Check current draw doesn't exceed board specifications

2. **UART Connection Points**
   ```
   ESP Board    ->  AC Unit
   TX (GPIO1)   ->  RX
   RX (GPIO3)   ->  TX
   GND          ->  GND
   5V           ->  5V (if powering from AC)
   ```

3. **Safety Checks**
   - [ ] AC unit is powered OFF during initial connection
   - [ ] All connections are secure
   - [ ] No exposed wires or short circuits
   - [ ] Ground connection is established

## Configuration Validation

### Step 1: Prepare Your Configuration

1. Copy the example secrets file:
   ```bash
   cp secrets.yaml.example secrets.yaml
   ```

2. Edit `secrets.yaml` with your network details:
   ```yaml
   wifi_ssid: "YourWiFiNetwork"
   wifi_password: "YourWiFiPassword"
   api_password: "YourAPIPassword"
   ota_password: "YourOTAPassword"
   ```

### Step 2: Validate YAML Syntax

Run the validation script:
```bash
./validate_config.sh
```

Or manually validate:
```bash
esphome config hisense_ac_modern.yaml
```

Expected output:
```
INFO Reading configuration hisense_ac_modern.yaml...
INFO Configuration is valid!
```

### Step 3: Compile Test

Perform a dry-run compile without uploading:
```bash
esphome compile hisense_ac_modern.yaml
```

Check for:
- No compilation errors
- All components are found
- Memory usage is within limits

## Initial Flash Procedure

### ESP32 Flashing

1. **Connect ESP32 via USB**
   ```bash
   # Find your device port
   ls /dev/tty* | grep -E 'USB|ACM'
   ```

2. **Initial Flash**
   ```bash
   esphome run hisense_ac_modern.yaml --device /dev/ttyUSB0
   ```

3. **Monitor Serial Output**
   ```bash
   esphome logs hisense_ac_modern.yaml --device /dev/ttyUSB0
   ```

### ESP8266 Flashing

1. **Use ESP8266 variant configuration**
   ```bash
   esphome run esp8266_variant.yaml --device /dev/ttyUSB0
   ```

2. **Important ESP8266 Notes:**
   - May require holding BOOT button during upload
   - Limited memory - monitor usage carefully
   - Software serial may be less reliable

### OTA Updates

After initial flash, subsequent updates can be done over-the-air:
```bash
esphome run hisense_ac_modern.yaml
```

## Component Testing

### 1. WiFi Connectivity
Monitor logs for successful connection:
```
[I][wifi:248]: WiFi Connected!
[I][wifi:249]: SSID: 'YourWiFiNetwork'
[I][wifi:250]: IP Address: 192.168.1.100
```

### 2. UART Communication
Check for UART initialization:
```
[I][uart:147]: Setting up UART...
[I][custom:052]: Hisense AC component initialized
```

### 3. Climate Component
Test basic climate operations:

```yaml
# In Home Assistant Developer Tools > Services
service: climate.set_temperature
target:
  entity_id: climate.hisense_ac
data:
  temperature: 22
```

Expected log output:
```
[I][climate:123]: Setting target temperature to 22°C
[I][custom:234]: Sending command: AA 23 AC 00 00 00 00 00 ...
```

### 4. Sensor Validation

Monitor sensor updates in logs:
```
[I][sensor:094]: 'Current Temperature': Got value 23.5°C
[I][sensor:094]: 'Current Humidity': Got value 45.0%
[I][sensor:094]: 'Outdoor Temperature': Got value 28.0°C
```

### 5. Switch Testing

Test each switch individually:
- Display toggle
- Health mode
- Quiet mode
- Eco mode

```yaml
# Test in Developer Tools
service: switch.turn_on
target:
  entity_id: switch.hisense_ac_display
```

## Home Assistant Integration

### 1. Auto-Discovery
The device should appear automatically in Home Assistant:
- Navigate to Settings > Devices & Services
- Look for "ESPHome" integration
- Device should appear as "Hisense AC"

### 2. Manual Addition
If not auto-discovered:
1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "ESPHome"
4. Enter device IP address
5. Enter API password from secrets.yaml

### 3. Entity Verification
Verify all entities are available:
- `climate.hisense_ac` - Main climate control
- `sensor.hisense_ac_current_temperature`
- `sensor.hisense_ac_current_humidity`
- `sensor.hisense_ac_outdoor_temperature`
- `switch.hisense_ac_display`
- `switch.hisense_ac_health_mode`
- `switch.hisense_ac_quiet_mode`
- `switch.hisense_ac_eco_mode`

### 4. Lovelace Card Test
Add a test card to your dashboard:
```yaml
type: thermostat
entity: climate.hisense_ac
features:
  - type: climate-hvac-modes
  - type: climate-preset-modes
```

## Troubleshooting

### Common Issues and Solutions

#### 1. No UART Communication
**Symptoms:** No response from AC, no status updates
**Solutions:**
- Verify TX/RX connections (try swapping them)
- Check baud rate matches AC unit (9600)
- Ensure ground connection is solid
- Use debug configuration for detailed logs

#### 2. WiFi Connection Issues
**Symptoms:** Device offline, frequent disconnections
**Solutions:**
- Check signal strength (add `wifi_signal` sensor)
- Verify credentials in secrets.yaml
- Try static IP configuration
- Increase `reboot_timeout` if needed

#### 3. Incomplete Status Updates
**Symptoms:** Some sensors show "Unknown"
**Solutions:**
- AC may need to be in operation
- Check packet parsing in logs
- Verify checksum calculations
- Some models may not support all features

#### 4. Commands Not Working
**Symptoms:** AC doesn't respond to commands
**Solutions:**
- Verify AC is not in local control lock mode
- Check command format in debug logs
- Ensure proper power state sequence
- Try manual command with test switches

#### 5. Memory Issues (ESP8266)
**Symptoms:** Random reboots, failed OTA updates
**Solutions:**
- Use ESP8266 variant configuration
- Disable unnecessary components
- Reduce log level in production
- Consider upgrading to ESP32

### Advanced Debugging

#### Enable Debug Logging
Use the debug configuration:
```bash
esphome run debug_config.yaml
```

#### Monitor Raw UART Data
Add to your configuration:
```yaml
uart:
  # ... existing config ...
  debug:
    direction: BOTH
    dummy_receiver: false
    after:
      delimiter: "\n"
    sequence:
      - lambda: UARTDebug::log_hex(direction, bytes, ' ');
```

#### Use Test Switches
The debug configuration includes test switches for manual command sending:
```yaml
switch:
  - platform: template
    name: "Send Test Command"
    turn_on_action:
      - lambda: |-
          // Send a test status request
          uint8_t test_cmd[] = {0xAA, 0x23, 0xAC, 0x00, 0x00, 0x00, 0x00, 0x00};
          // ... calculate checksum and send
```

## Debug Logging

### Log Levels
Configure appropriate log levels for different components:

```yaml
logger:
  level: DEBUG  # Global level
  logs:
    sensor: INFO
    climate: DEBUG
    uart: DEBUG
    custom: VERBOSE
```

### Interpreting Logs

#### Successful Communication
```
[D][uart:114]: Received: AA.23.AC.00.00.00.00.00... (OK)
[D][custom:156]: Parsing status packet...
[D][custom:167]: Temperature: 23°C, Humidity: 45%
```

#### Failed Communication
```
[W][custom:234]: Checksum mismatch! Expected: 0x5A, Got: 0x5B
[W][custom:245]: Invalid packet header: 0xBB (expected 0xAA)
```

### Performance Monitoring
Monitor system performance:
```yaml
sensor:
  - platform: uptime
    name: "Uptime"
  
  - platform: wifi_signal
    name: "WiFi Signal"
    
  - platform: internal_temperature
    name: "CPU Temperature"  # ESP32 only
```

## Validation Checklist

Before considering your installation complete:

- [ ] Device connects to WiFi reliably
- [ ] All sensors report valid values
- [ ] Climate control responds to commands
- [ ] Temperature changes are reflected accurately
- [ ] Switches toggle without errors
- [ ] Home Assistant integration is stable
- [ ] No unexpected reboots in 24-hour period
- [ ] OTA updates work successfully
- [ ] Power consumption is within expected range

## Getting Help

If you encounter issues not covered in this guide:

1. **Enable debug logging** and collect logs for at least one full operation cycle
2. **Document your hardware setup** including board model and wiring
3. **Note your AC model** and any specific behaviors
4. **Check the GitHub issues** for similar problems
5. **Create a detailed issue** with logs, configuration, and hardware details

## Safety Reminder

⚠️ **Always disconnect power when making hardware changes**
⚠️ **Never work on AC unit with mains power connected**
⚠️ **Use proper insulation for all connections**
⚠️ **Follow local electrical codes and regulations**