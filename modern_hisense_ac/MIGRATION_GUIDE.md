# Migration Guide: Old Configuration to Modern Hisense AC

This guide helps you migrate from the older Hisense AC ESPHome configurations to the new modernized version with improved features and reliability.

## Table of Contents
- [Overview of Changes](#overview-of-changes)
- [Backup Procedures](#backup-procedures)
- [Migration Steps](#migration-steps)
- [Entity ID Mapping](#entity-id-mapping)
- [Breaking Changes](#breaking-changes)
- [Automation Updates](#automation-updates)
- [Rollback Procedure](#rollback-procedure)

## Overview of Changes

### Key Improvements in Modern Configuration
- ✅ **External Component Structure**: No more custom platform warnings
- ✅ **Modular Design**: Separated C++ files for better maintainability
- ✅ **Enhanced Error Handling**: Improved checksum validation and packet parsing
- ✅ **Better State Management**: Reliable state tracking and synchronization
- ✅ **Extended Features**: Support for more AC modes and settings
- ✅ **Improved Logging**: Better debug capabilities and error reporting
- ✅ **Home Assistant Integration**: Native climate platform support
- ✅ **Multi-Board Support**: Separate configs for ESP32 and ESP8266

### Configuration Structure Changes

| Old Structure | New Structure |
|--------------|---------------|
| Single YAML file with embedded C++ | External component structure |
| Custom platform with includes | External component with Python + C++ |
| Inline lambda functions | Organized component files |
| Basic climate platform | Full climate platform with presets |
| Limited sensor support | Comprehensive sensor suite |
| No variant support | ESP32/ESP8266 variants |

## Backup Procedures

### Step 1: Backup Current Configuration

1. **Save your existing YAML files:**
   ```bash
   mkdir ~/hisense_ac_backup_$(date +%Y%m%d)
   cp *.yaml ~/hisense_ac_backup_$(date +%Y%m%d)/
   cp *.h ~/hisense_ac_backup_$(date +%Y%m%d)/
   ```

2. **Export Home Assistant entities:**
   - Go to Developer Tools > Services
   - Call service: `recorder.purge` with `keep_days: 0` to create a backup point
   - Download your Home Assistant backup from Settings > System > Backups

3. **Document your automations:**
   ```yaml
   # Save automation IDs and configurations that use the AC
   grep -r "climate.room_ac" ~/.homeassistant/automations.yaml > ac_automations_backup.txt
   ```

### Step 2: Record Current Settings

Document your current working configuration:
```yaml
# Create a settings backup file
cat > current_settings.yaml << EOF
device_name: $(grep "name:" *.yaml | head -1)
wifi_ssid: $(grep "ssid:" *.yaml | head -1)
api_password: $(grep "api:" *.yaml -A 2 | grep password)
ota_password: $(grep "ota:" *.yaml -A 2 | grep password)
uart_pins:
  tx: $(grep "tx_pin:" *.yaml | head -1)
  rx: $(grep "rx_pin:" *.yaml | head -1)
EOF
```

## Migration Steps

### Step 1: Prepare New Configuration

1. **Copy the entire modern_hisense_ac folder:**
   ```bash
   # Copy the complete folder including components
   cp -r modern_hisense_ac /path/to/esphome/
   cd /path/to/esphome/modern_hisense_ac/
   ```
   
   **Important**: The folder structure must be preserved:
   ```
   modern_hisense_ac/
   ├── components/
   │   └── hisense_ac/
   │       ├── __init__.py
   │       ├── climate.py
   │       ├── hisense_ac.h
   │       └── hisense_ac.cpp
   ├── hisense_ac_modern.yaml
   ├── esp32_variant.yaml
   ├── esp8266_variant.yaml
   └── ...
   ```

2. **Create your secrets file:**
   ```bash
   cp secrets.yaml.example secrets.yaml
   ```

3. **Transfer your settings:**
   Edit `secrets.yaml` with your backed-up values:
   ```yaml
   wifi_ssid: "YourExistingSSID"
   wifi_password: "YourExistingPassword"
   api_password: "YourExistingAPIPassword"  # Keep same for smooth transition
   ota_password: "YourExistingOTAPassword"  # Keep same for OTA update
   ```

### Step 2: Customize Device Configuration

1. **Choose your board variant:**
   - For ESP32: Use `esp32_variant.yaml`
   - For ESP8266: Use `esp8266_variant.yaml`
   - For debugging: Use `debug_config.yaml`

2. **Update device-specific settings:**
   ```yaml
   esphome:
     name: "room-ac"  # Keep your existing name for entity continuity
     friendly_name: "Room AC"  # Your existing friendly name
   
   # If using different UART pins than default:
   uart:
     tx_pin: GPIO1  # Your existing TX pin
     rx_pin: GPIO3  # Your existing RX pin
   ```

3. **Preserve static IP (if used):**
   ```yaml
   wifi:
     manual_ip:
       static_ip: 192.168.1.100  # Your existing IP
       gateway: 192.168.1.1
       subnet: 255.255.255.0
   ```

### Step 3: Test Configuration

1. **Validate the new configuration:**
   ```bash
   # For ESP32
   esphome config esp32_variant.yaml
   
   # For ESP8266
   esphome config esp8266_variant.yaml
   ```

2. **Compile without uploading:**
   ```bash
   # For ESP32
   esphome compile esp32_variant.yaml
   
   # For ESP8266
   esphome compile esp8266_variant.yaml
   ```

### Step 4: Deploy New Configuration

#### Option A: OTA Update (Recommended)
If your device is currently online and accessible:

```bash
# This will update over-the-air
# For ESP32
esphome run esp32_variant.yaml

# For ESP8266
esphome run esp8266_variant.yaml
```

#### Option B: Serial Flash
If OTA fails or device is inaccessible:

```bash
# Connect via USB and flash
# For ESP32
esphome run esp32_variant.yaml --device /dev/ttyUSB0

# For ESP8266
esphome run esp8266_variant.yaml --device /dev/ttyUSB0
```

### Step 5: Verify in Home Assistant

1. **Check device appears online:**
   - Navigate to Settings > Devices & Services > ESPHome
   - Verify your device shows as "Online"

2. **Confirm all entities are available:**
   - Click on the device
   - Verify all expected entities are present

## Entity ID Mapping

### Climate Entity

| Old Entity ID | New Entity ID | Notes |
|--------------|---------------|-------|
| `climate.room_ac` | `climate.hisense_ac` | Main climate control |
| `climate.room_ac_climate` | `climate.hisense_ac` | Consolidated naming |

### Sensor Entities

| Old Entity ID | New Entity ID | Notes |
|--------------|---------------|-------|
| `sensor.room_ac_temperature` | `sensor.hisense_ac_current_temperature` | More descriptive |
| `sensor.room_ac_humidity` | `sensor.hisense_ac_current_humidity` | More descriptive |
| `sensor.room_ac_outdoor_temp` | `sensor.hisense_ac_outdoor_temperature` | Consistent naming |
| N/A | `sensor.hisense_ac_wifi_signal` | New diagnostic sensor |
| N/A | `sensor.hisense_ac_uptime` | New diagnostic sensor |

### Switch Entities

| Old Entity ID | New Entity ID | Notes |
|--------------|---------------|-------|
| `switch.room_ac_display` | `switch.hisense_ac_display` | Display toggle |
| `switch.room_ac_health` | `switch.hisense_ac_health_mode` | More descriptive |
| N/A | `switch.hisense_ac_quiet_mode` | New feature |
| N/A | `switch.hisense_ac_eco_mode` | New feature |

### Select Entities

| Old Entity ID | New Entity ID | Notes |
|--------------|---------------|-------|
| `select.room_ac_mode` | Integrated in climate entity | Uses climate.set_hvac_mode |
| `select.room_ac_fan` | Integrated in climate entity | Uses climate.set_fan_mode |
| `select.room_ac_swing` | `select.hisense_ac_vertical_swing` | More specific |
| N/A | `select.hisense_ac_horizontal_swing` | New feature |

## Breaking Changes

### 1. Climate Platform Changes

**Old Method (Custom Platform):**
```yaml
esphome:
  includes:
    - hisense_ac.h

climate:
  - platform: custom
    lambda: |-
      auto my_climate = new HisenseAC();
      App.register_component(my_climate);
      return {my_climate};
```

**New Method (External Component):**
```yaml
# Load the external component
external_components:
  - source:
      type: local
      path: components
    components: [hisense_ac]

# No includes needed!
climate:
  - platform: hisense_ac
    name: "Hisense AC"
    uart_id: ac_uart
    compressor_frequency_sensor:
      name: "Compressor Frequency"
    outdoor_temperature_sensor:
      name: "Outdoor Temperature"
    pipe_temperature_sensor:
      name: "Pipe Temperature"
```

### 2. Temperature Scale

- Old: Some configs used Fahrenheit by default
- New: Celsius is default, Fahrenheit configurable
- **Action Required**: Update automations if using Fahrenheit

### 3. Fan Mode Values

| Old Value | New Value |
|-----------|-----------|
| `Auto` | `auto` |
| `Low` | `low` |
| `Medium` | `medium` |
| `High` | `high` |
| `Turbo` | `turbo` |

### 4. Preset Modes

New configuration supports preset modes:
- `eco` - Energy saving mode
- `sleep` - Sleep mode
- `boost` - Turbo mode

## Automation Updates

### Update Entity IDs in Automations

1. **Find affected automations:**
   ```bash
   grep -n "room_ac" ~/.homeassistant/automations.yaml
   ```

2. **Update entity references:**

**Old automation:**
```yaml
- alias: "AC Auto Off"
  trigger:
    platform: numeric_state
    entity_id: sensor.room_ac_temperature
    above: 25
  action:
    service: climate.turn_off
    entity_id: climate.room_ac
```

**Updated automation:**
```yaml
- alias: "AC Auto Off"
  trigger:
    platform: numeric_state
    entity_id: sensor.hisense_ac_current_temperature
    above: 25
  action:
    service: climate.turn_off
    entity_id: climate.hisense_ac
```

### Update Service Calls

**Old service call:**
```yaml
service: climate.set_temperature
data:
  entity_id: climate.room_ac
  temperature: 22
  hvac_mode: cool
```

**New service call:**
```yaml
service: climate.set_temperature
target:
  entity_id: climate.hisense_ac
data:
  temperature: 22
  hvac_mode: cool
```

### Update Lovelace Cards

**Old card configuration:**
```yaml
type: thermostat
entity: climate.room_ac
```

**New card configuration:**
```yaml
type: thermostat
entity: climate.hisense_ac
features:
  - type: climate-hvac-modes
  - type: climate-preset-modes
```

## Rollback Procedure

If you need to revert to the old configuration:

### Step 1: Restore Old Configuration

```bash
# Copy back your backed-up files
cp ~/hisense_ac_backup_*/room_ac.yaml .
```

### Step 2: Flash Old Firmware

```bash
# Upload the old configuration
esphome run room_ac.yaml
```

### Step 3: Restore Automations

```bash
# Restore your automations backup
cp ~/hisense_ac_backup_*/automations.yaml ~/.homeassistant/
```

### Step 4: Restart Home Assistant

```bash
ha core restart
```

## Troubleshooting Migration Issues

### Issue: Entity IDs Don't Match

**Solution:** Create template sensors for compatibility:
```yaml
# In Home Assistant configuration.yaml
template:
  - sensor:
      - name: "Room AC Temperature"
        unique_id: room_ac_temperature_compat
        state: "{{ states('sensor.hisense_ac_current_temperature') }}"
        unit_of_measurement: "°C"
```

### Issue: Automations Not Triggering

**Solution:** Check and update:
1. Entity IDs in triggers
2. Entity IDs in conditions
3. Entity IDs in actions
4. Service call formats (use `target:` key)

### Issue: OTA Update Fails

**Solution:** 
1. Ensure same OTA password in secrets.yaml
2. Try increasing timeout:
   ```yaml
   ota:
     password: !secret ota_password
     safe_mode: true
     reboot_timeout: 10min
   ```
3. Use serial flash as fallback

### Issue: Missing Features After Migration

**Solution:** Some features may need explicit enabling:
```yaml
# Add missing switches if needed
switch:
  - platform: template
    name: "Legacy Feature"
    lambda: |-
      // Custom implementation
```

## Post-Migration Checklist

- [ ] Device appears online in Home Assistant
- [ ] All climate controls work (temperature, mode, fan)
- [ ] Sensors report correct values
- [ ] Switches function properly
- [ ] Automations trigger correctly
- [ ] Lovelace cards display properly
- [ ] Historical data is preserved (if needed)
- [ ] No errors in Home Assistant logs
- [ ] No errors in ESPHome logs

## Getting Support

If you encounter issues during migration:

1. **Check logs:**
   ```bash
   # For ESP32
   esphome logs esp32_variant.yaml
   
   # For ESP8266
   esphome logs esp8266_variant.yaml
   
   # For debugging
   esphome logs debug_config.yaml
   ```

2. **Review Home Assistant logs:**
   - Settings > System > Logs

3. **Create detailed issue report with:**
   - Old configuration file
   - New configuration file
   - Error messages
   - ESPHome version
   - Home Assistant version

## Summary

The migration to the modern external component configuration provides:
- **No more custom platform warnings** with modern ESPHome
- Better reliability and error handling
- More features and control options
- Improved Home Assistant integration
- Easier maintenance and updates
- Clean separation of Python and C++ code

While some entity IDs will change, the migration process is straightforward and can be reversed if needed. Take time to backup, test thoroughly, and update your automations for a smooth transition.