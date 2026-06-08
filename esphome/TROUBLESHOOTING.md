# Hisense AC Component Troubleshooting Guide

## Table of Contents
- [Missing Entities in Home Assistant](#missing-entities-in-home-assistant)
- [Verifying Device Connection](#verifying-device-connection)
- [Component Loading Issues](#component-loading-issues)
- [UART Communication Problems](#uart-communication-problems)
- [ESP-01 Specific Issues](#esp-01-specific-issues)
- [Debug Logging](#debug-logging)
- [Common Error Messages](#common-error-messages)

## Missing Entities in Home Assistant

If you don't see the expected entities in Home Assistant after deploying the configuration:

### Expected Entities
You should see these entities when the component is working correctly:
- `climate.hisense_ac` - Main climate control
- `sensor.compressor_frequency` - Compressor frequency in Hz
- `sensor.outdoor_temperature` - Outdoor temperature sensor
- `sensor.pipe_temperature` - Pipe temperature sensor

### Troubleshooting Steps

1. **Check if the device is online in ESPHome Dashboard**
   - Open ESPHome dashboard
   - Look for your device - it should show as "ONLINE" with a green indicator
   - If offline, check WiFi configuration and power supply

2. **Verify the device appears in Home Assistant**
   - Go to Settings → Devices & Services → ESPHome
   - Your device should be listed there
   - If not, check API configuration and encryption key

3. **Check ESPHome logs for component registration**
   ```bash
   # View logs from ESPHome dashboard or use command line:
   esphome logs modern_hisense_ac/test_basic.yaml
   ```
   
   Look for these key messages:
   ```
   [D][hisense_ac:xxx]: Setting up Hisense AC Climate...
   [D][climate:xxx]: 'Hisense AC' - Setup complete
   ```

4. **Use the test configuration**
   Deploy `test_basic.yaml` first to verify basic connectivity:
   ```bash
   esphome run modern_hisense_ac/test_basic.yaml
   ```

## Verifying Device Connection

### Step 1: Check Basic Connectivity
The test configuration includes fallback entities. Even if the AC component fails, you should see:
- WiFi Signal sensor
- Uptime sensor
- Connection Status binary sensor
- IP Address text sensor

If these don't appear, the device isn't connecting to Home Assistant at all.

### Step 2: Check API Connection
1. In Home Assistant, go to Developer Tools → Services
2. Search for `esphome.hisense_ac_test` services
3. If no services appear, the API connection is not working

### Step 3: Verify mDNS Discovery
```yaml
# Add to your configuration if having discovery issues:
mdns:
  disabled: false
```

### Step 4: Manual Integration
If auto-discovery fails:
1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "ESPHome"
4. Enter the device IP address and port 6053
5. Enter your API encryption key

## Component Loading Issues

### Check External Component Loading

1. **Verify component files exist**
   ```
   modern_hisense_ac/components/hisense_ac/
   ├── __init__.py
   ├── climate.py
   ├── hisense_ac.cpp
   └── hisense_ac.h
   ```

2. **Check compilation output**
   During compilation, you should see:
   ```
   Compiling .pioenvs/hisense-ac/src/hisense_ac/hisense_ac.cpp.o
   ```

3. **Common component errors**
   - `Component not found: hisense_ac` - Check external_components path
   - `No module named 'hisense_ac'` - Python files missing or incorrect
   - `undefined reference` - C++ compilation issues

### Fix Component Registration Issues

If the component compiles but doesn't create entities:

1. **Enable verbose logging**
   ```yaml
   logger:
     level: VERBOSE
     logs:
       hisense_ac: VERY_VERBOSE
       component: DEBUG
   ```

2. **Check for registration messages**
   ```
   [V][component:xxx]: Component hisense_ac.climate registered
   [D][climate:xxx]: Setting up climate platform
   ```

3. **Verify UART is configured**
   The component requires UART to be properly configured before it can initialize.

## UART Communication Problems

### Testing UART Communication

1. **Enable UART debugging**
   ```yaml
   uart:
     id: ac_uart
     tx_pin: GPIO1  # For ESP-01
     rx_pin: GPIO3  # For ESP-01
     baud_rate: 9600
     debug:
       direction: BOTH
       dummy_receiver: true  # Test without AC unit
       after:
         delimiter: "\n"
   ```

2. **Check for UART data**
   Look in logs for:
   ```
   [D][uart_debug:xxx]: >>> F4:F5:00:40:0C...  (TX data)
   [D][uart_debug:xxx]: <<< F4:F5:01:40:29...  (RX data)
   ```

3. **No data received?**
   - Check wiring connections
   - Verify baud rate (9600 is standard)
   - Test with a USB-to-UART adapter
   - Check if AC unit is powered on

### UART Wiring Verification

For ESP-01:
```
ESP-01          AC Unit
------          -------
TX (GPIO1) ---> RX
RX (GPIO3) <--- TX
GND        ---- GND
VCC (3.3V) ---- VCC
```

**Important:** Some AC units use 5V logic. Use a level shifter if needed!

## ESP-01 Specific Issues

### Memory Limitations
ESP-01 has only 1MB flash and limited RAM. Optimize your configuration:

1. **Remove unnecessary components**
   ```yaml
   # Comment out if not needed:
   # web_server:
   # captive_portal:
   ```

2. **Use recommended framework**
   ```yaml
   esp8266:
     board: esp01_1m
     framework:
       version: recommended
   ```

3. **Monitor free heap**
   ```yaml
   sensor:
     - platform: template
       name: "Free Heap"
       lambda: return ESP.getFreeHeap();
       unit_of_measurement: bytes
   ```

### GPIO Limitations
ESP-01 has limited GPIOs:
- GPIO0: Boot mode (use with caution)
- GPIO1: TX (UART)
- GPIO2: Built-in LED (if available)
- GPIO3: RX (UART)

### Power Supply Issues
ESP-01 requires stable 3.3V power:
- Use a dedicated 3.3V regulator
- Add capacitors (100µF + 0.1µF) near the ESP-01
- Don't power from the AC unit's 5V without regulation

## Debug Logging

### Enable Comprehensive Logging

```yaml
logger:
  level: DEBUG
  logs:
    hisense_ac: VERY_VERBOSE
    climate: DEBUG
    sensor: DEBUG
    uart: DEBUG
    uart_debug: DEBUG
    component: DEBUG
    api: WARN  # Reduce API logs to see other messages
    wifi: WARN # Reduce WiFi logs
```

### Key Log Messages to Look For

**Successful initialization:**
```
[C][hisense_ac:xxx]: Hisense AC Climate:
[C][hisense_ac:xxx]:   Name: Hisense AC
[C][hisense_ac:xxx]:   UART configured: YES
[D][hisense_ac:xxx]: Querying initial status...
```

**Communication working:**
```
[V][hisense_ac:xxx]: Sending status query command
[D][hisense_ac:xxx]: Processing status update
[D][hisense_ac:xxx]: Status update complete - Temp: 24/22°C, Mode: 2, Power: ON
```

**Entity registration:**
```
[C][climate:xxx]: Climate 'Hisense AC'
[C][sensor:xxx]: Sensor 'Compressor Frequency'
```

### Using ESPHome CLI for Debugging

```bash
# Compile and show verbose output
esphome compile modern_hisense_ac/test_basic.yaml -v

# Upload and monitor logs
esphome run modern_hisense_ac/test_basic.yaml

# Just monitor logs (device must be online)
esphome logs modern_hisense_ac/test_basic.yaml
```

## Common Error Messages

### "Component hisense_ac not found"
**Solution:** Check external_components configuration:
```yaml
external_components:
  - source:
      type: local
      path: components  # Relative to the YAML file
    components: [hisense_ac]
```

### "Platform not found: 'climate.hisense_ac'"
**Solution:** The component isn't loading. Check:
1. Python files are present and valid
2. No syntax errors in Python code
3. Dependencies are declared correctly

### "UART Buffer overflow"
**Solution:** AC is sending data too fast or invalid data:
```yaml
uart:
  rx_buffer_size: 512  # Increase buffer size
```

### "Checksum mismatch"
**Solution:** Communication errors. Check:
1. Wiring connections
2. Baud rate (should be 9600)
3. Power supply stability
4. Cable length (keep under 1 meter)

### "No response from AC unit"
**Solution:**
1. Verify AC unit is powered on
2. Check UART connections
3. Try swapping TX/RX wires
4. Ensure common ground between ESP and AC

## Testing Without AC Unit

To test the component without connecting to an AC unit:

```yaml
uart:
  id: ac_uart
  tx_pin: GPIO1
  rx_pin: GPIO3
  baud_rate: 9600
  debug:
    direction: BOTH
    dummy_receiver: true  # Simulates receiving data
    after:
      delimiter: "\n"
    sequence:
      - lambda: |-
          // Simulate AC response for testing
          if (direction == UART_DIRECTION_TX) {
            ESP_LOGD("test", "Would send to AC: %s", 
                     format_hex_pretty(bytes).c_str());
          }
```

## Getting Help

If you're still having issues:

1. **Collect diagnostic information:**
   - Full ESPHome logs from boot
   - Your YAML configuration (remove passwords)
   - Photo of wiring connections
   - ESPHome and Home Assistant versions

2. **Check for updates:**
   ```bash
   # Update ESPHome
   pip install -U esphome
   
   # Clean build files
   esphome clean modern_hisense_ac/your_config.yaml
   ```

3. **Report issues with:**
   - Description of the problem
   - Expected behavior
   - Actual behavior
   - Steps to reproduce
   - Diagnostic information from step 1

## Quick Checklist

- [ ] Device shows as online in ESPHome dashboard
- [ ] Device appears in Home Assistant integrations
- [ ] Test configuration deploys successfully
- [ ] Fallback sensors (WiFi, Uptime) are visible
- [ ] UART debug shows data being sent/received
- [ ] Component shows in compilation output
- [ ] No error messages in logs during setup
- [ ] Climate entity appears in Home Assistant
- [ ] Sensor entities appear (if configured)
- [ ] Can control AC from Home Assistant