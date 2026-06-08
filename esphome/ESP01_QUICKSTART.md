# ESP-01 Quick Start Guide for Hisense AC Component

## Problem: No Entities Showing in Home Assistant

If you've deployed to ESP-01 but don't see any entities in Home Assistant, follow these steps:

## Step 1: Deploy the Test Configuration First

1. **Use the test configuration** (`test_basic.yaml` or `esp01_variant.yaml`)
2. **Compile and upload:**
   ```bash
   esphome run modern_hisense_ac/esp01_variant.yaml
   ```

## Step 2: Verify Basic Connectivity

After deployment, you should see these entities in Home Assistant within 1-2 minutes:
- `sensor.hisense_ac_wifi` - WiFi signal strength
- `sensor.hisense_ac_uptime` - Device uptime
- `binary_sensor.hisense_ac_connection` - Connection status

**If you don't see these basic entities:**
- The device isn't connecting to Home Assistant
- Check your API encryption key
- Verify WiFi credentials

## Step 3: Check ESPHome Integration

1. Go to **Settings → Devices & Services → ESPHome**
2. Look for your device (should show as "hisense-ac-esp01")
3. If not present, add manually:
   - Click **"+ Add Integration"**
   - Choose **ESPHome**
   - Enter device IP and port 6053
   - Enter your API encryption key

## Step 4: Monitor Logs for Issues

```bash
esphome logs modern_hisense_ac/esp01_variant.yaml
```

Look for these key messages:

✅ **Good signs:**
```
[I][app:029]: Running through setup()...
[I][hisense_ac:xxx]: Setting up Hisense AC Climate...
[I][climate:xxx]: 'Hisense AC' - Setup complete
```

❌ **Problem indicators:**
```
[E][component:xxx]: Component hisense_ac.climate was marked as failed
[W][hisense_ac:xxx]: No response from AC unit
```

## Step 5: Expected Entities When Working

Once properly configured and connected to the AC unit, you should see:

### Main Control
- `climate.hisense_ac` - Main thermostat control

### Sensors
- `sensor.hisense_ac_compressor` - Compressor frequency
- `sensor.hisense_ac_outdoor_temp` - Outdoor temperature
- `sensor.hisense_ac_pipe_temp` - Pipe temperature


### Diagnostic Entities
- `sensor.hisense_ac_wifi` - WiFi signal
- `sensor.hisense_ac_uptime` - Uptime
- `sensor.hisense_ac_free_memory` - Free heap
- `binary_sensor.hisense_ac_connection` - Connection status

## Common ESP-01 Issues and Solutions

### Issue 1: Device Goes Offline Frequently
**Solution:** Power supply issue
- ESP-01 needs stable 3.3V (not 5V!)
- Use a dedicated 3.3V regulator (AMS1117-3.3)
- Add 100µF capacitor near ESP-01 power pins

### Issue 2: No Climate Entity Despite Other Entities Working
**Solution:** Component not loading properly
1. Clean build files:
   ```bash
   esphome clean modern_hisense_ac/esp01_variant.yaml
   ```
2. Rebuild and upload:
   ```bash
   esphome run modern_hisense_ac/esp01_variant.yaml
   ```

### Issue 3: UART Communication Not Working
**Solution:** Wiring or configuration issue

Check wiring:
```
ESP-01 Pin    AC Unit
----------    -------
GPIO1 (TX) -> RX
GPIO3 (RX) <- TX
GND        -- GND
VCC (3.3V) -- 3.3V (NOT 5V!)
```

### Issue 4: Out of Memory Errors
**Solution:** Remove unnecessary components
```yaml
# Comment out these if not needed:
# time:
#   - platform: homeassistant

# Reduce sensor update frequency:
sensor:
  - platform: wifi_signal
    update_interval: 600s  # 10 minutes instead of 5
```

## Testing Without AC Unit Connected

To verify the component loads without the AC unit:

1. **Enable dummy UART receiver:**
```yaml
uart:
  id: ac_uart
  tx_pin: GPIO1
  rx_pin: GPIO3
  baud_rate: 9600
  debug:
    direction: BOTH
    dummy_receiver: true  # Simulates responses
```

2. **Check logs for component initialization:**
```
[I][climate:xxx]: Setting up climate
[I][hisense_ac:xxx]: Component name: Hisense AC
```

## Quick Deployment Commands

```bash
# Clean previous build
esphome clean modern_hisense_ac/esp01_variant.yaml

# Compile only (check for errors)
esphome compile modern_hisense_ac/esp01_variant.yaml

# Compile and upload
esphome run modern_hisense_ac/esp01_variant.yaml

# Monitor logs
esphome logs modern_hisense_ac/esp01_variant.yaml
```

## If Nothing Works

1. **Start with absolute minimum:**
   - Deploy a basic ESP-01 config without the AC component
   - Verify it connects to WiFi and Home Assistant
   - Add the AC component once basic connectivity works

2. **Check component files exist:**
   ```
   components/hisense_ac/
   ├── __init__.py
   ├── climate.py
   ├── hisense_ac.cpp
   └── hisense_ac.h
   ```

3. **Report issue with:**
   - Full log output from boot
   - Your exact wiring setup
   - ESP-01 module version (ESP-01 or ESP-01S)
   - Power supply details

## Success Checklist

- [ ] ESP-01 connects to WiFi
- [ ] Device appears in ESPHome integration
- [ ] Basic sensors (WiFi, Uptime) visible
- [ ] Climate entity appears
- [ ] Can control AC from Home Assistant
- [ ] AC responds to commands
- [ ] Temperature readings update