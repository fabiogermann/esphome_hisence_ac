#include "hisense_ac.h"
#include "esphome/core/log.h"

namespace esphome {
namespace hisense_ac {

static const char *const TAG = "hisense_ac";

void HisenseClimate::setup() {
  ESP_LOGCONFIG(TAG, "Setting up Hisense AC Climate...");
  ESP_LOGD(TAG, "Component name: %s", this->name_.c_str());
  
  // Set supported features
  this->target_temperature = this->target_temperature_;
  this->current_temperature = this->current_temperature_;
  
  // Query initial status
  ESP_LOGD(TAG, "Querying initial status...");
  this->query_status();
}

void HisenseClimate::loop() {
  // Read UART data
  while (this->available()) {
    uint8_t byte;
    this->read_byte(&byte);
    
    rx_buffer_.push_back(byte);
    
    // Check for frame completion
    if (rx_buffer_.size() >= 4) {
      size_t len = rx_buffer_.size();
      if (rx_buffer_[len - 2] == FRAME_FOOTER_1 && 
          rx_buffer_[len - 1] == FRAME_FOOTER_2) {
        // Frame complete, try to parse
        if (parse_frame(rx_buffer_.data(), len)) {
          waiting_for_response_ = false;
          retry_count_ = 0;
        }
        rx_buffer_.clear();
      }
    }
    
    // Prevent buffer overflow
    if (rx_buffer_.size() > MAX_BUFFER_SIZE) {
      ESP_LOGW(TAG, "RX buffer overflow, clearing");
      rx_buffer_.clear();
    }
  }
  
  // Handle command queue
  uint32_t now = millis();
  if (!tx_queue_.empty() && !waiting_for_response_) {
    if (now - last_command_time_ >= COMMAND_TIMEOUT_MS) {
      auto cmd = tx_queue_.front();
      this->write_array(cmd.data(), cmd.size());
      this->flush();
      waiting_for_response_ = true;
      last_command_time_ = now;
      
      // Handle retries
      if (++retry_count_ >= MAX_RETRIES) {
        ESP_LOGW(TAG, "Command failed after %d retries", MAX_RETRIES);
        tx_queue_.pop();
        retry_count_ = 0;
        waiting_for_response_ = false;
      }
    }
  }
  
  // Periodic status query
  if (now - last_query_time_ >= QUERY_INTERVAL_MS) {
    this->query_status();
    last_query_time_ = now;
  }
}

void HisenseClimate::dump_config() {
  ESP_LOGCONFIG(TAG, "Hisense AC Climate:");
  ESP_LOGCONFIG(TAG, "  Name: %s", this->name_.c_str());
  ESP_LOGCONFIG(TAG, "  Min Temperature: 16°C");
  ESP_LOGCONFIG(TAG, "  Max Temperature: 32°C");
  ESP_LOGCONFIG(TAG, "  UART configured: %s", this->parent_ ? "YES" : "NO");
  ESP_LOGCONFIG(TAG, "  Sensors:");
  ESP_LOGCONFIG(TAG, "    Compressor Frequency: %s",
                compressor_frequency_sensor_ ? "YES" : "NO");
  ESP_LOGCONFIG(TAG, "    Outdoor Temperature: %s",
                outdoor_temperature_sensor_ ? "YES" : "NO");
  ESP_LOGCONFIG(TAG, "    Pipe Temperature: %s",
                pipe_temperature_sensor_ ? "YES" : "NO");
}

climate::ClimateTraits HisenseClimate::traits() {
  auto traits = climate::ClimateTraits();
  
  traits.set_supports_current_temperature(true);
  traits.set_visual_min_temperature(16);
  traits.set_visual_max_temperature(32);
  traits.set_visual_temperature_step(1);
  
  traits.set_supported_modes({
    climate::CLIMATE_MODE_OFF,
    climate::CLIMATE_MODE_COOL,
    climate::CLIMATE_MODE_HEAT,
    climate::CLIMATE_MODE_DRY,
    climate::CLIMATE_MODE_FAN_ONLY,
    climate::CLIMATE_MODE_HEAT_COOL  // Auto mode
  });
  
  traits.set_supported_fan_modes({
    climate::CLIMATE_FAN_AUTO,
    climate::CLIMATE_FAN_QUIET,
    climate::CLIMATE_FAN_LOW,
    climate::CLIMATE_FAN_MEDIUM,
    climate::CLIMATE_FAN_HIGH
  });
  
  traits.set_supported_swing_modes({
    climate::CLIMATE_SWING_OFF,
    climate::CLIMATE_SWING_VERTICAL,
    climate::CLIMATE_SWING_HORIZONTAL,
    climate::CLIMATE_SWING_BOTH
  });
  
  traits.set_supported_presets({
    climate::CLIMATE_PRESET_NONE,
    climate::CLIMATE_PRESET_ECO,
    climate::CLIMATE_PRESET_BOOST,  // Turbo
    climate::CLIMATE_PRESET_SLEEP
  });
  
  traits.set_supports_action(true);
  
  return traits;
}

void HisenseClimate::control(const climate::ClimateCall &call) {
  bool needs_update = false;
  
  // Handle mode changes
  if (call.get_mode().has_value()) {
    climate::ClimateMode mode = *call.get_mode();
    
    if (mode == climate::CLIMATE_MODE_OFF) {
      if (power_state_) {
        send_power_command(false);
        power_state_ = false;
        needs_update = true;
      }
    } else {
      if (!power_state_) {
        send_power_command(true);
        power_state_ = true;
      }
      
      ACMode ac_mode = climate_mode_to_ac_mode(mode);
      if (ac_mode != current_mode_) {
        send_mode_command(ac_mode);
        current_mode_ = ac_mode;
        needs_update = true;
      }
    }
    
    this->mode = mode;
  }
  
  // Handle temperature changes
  if (call.get_target_temperature().has_value()) {
    float temp = *call.get_target_temperature();
    uint8_t temp_int = static_cast<uint8_t>(temp);
    
    if (temp_int != target_temperature_) {
      send_temperature_command(temp_int);
      target_temperature_ = temp_int;
      this->target_temperature = temp;
      needs_update = true;
    }
  }
  
  // Handle fan mode changes
  if (call.get_fan_mode().has_value()) {
    climate::ClimateFanMode fan = *call.get_fan_mode();
    FanSpeed speed = climate_fan_to_fan_speed(fan);
    
    if (speed != fan_speed_) {
      send_fan_command(speed);
      fan_speed_ = speed;
      this->fan_mode = fan;
      needs_update = true;
    }
  }
  
  // Handle swing mode changes
  if (call.get_swing_mode().has_value()) {
    climate::ClimateSwingMode swing = *call.get_swing_mode();
    bool vert = false, horiz = false;
    
    switch (swing) {
      case climate::CLIMATE_SWING_VERTICAL:
        vert = true;
        break;
      case climate::CLIMATE_SWING_HORIZONTAL:
        horiz = true;
        break;
      case climate::CLIMATE_SWING_BOTH:
        vert = true;
        horiz = true;
        break;
      default:
        break;
    }
    
    if (vert != swing_vertical_ || horiz != swing_horizontal_) {
      send_swing_command(vert, horiz);
      swing_vertical_ = vert;
      swing_horizontal_ = horiz;
      this->swing_mode = swing;
      needs_update = true;
    }
  }
  
  // Handle preset changes
  if (call.get_preset().has_value()) {
    climate::ClimatePreset preset = *call.get_preset();
    
    switch (preset) {
      case climate::CLIMATE_PRESET_ECO:
        if (!eco_mode_) {
          send_eco_command(true);
          eco_mode_ = true;
          turbo_mode_ = false;
          needs_update = true;
        }
        break;
        
      case climate::CLIMATE_PRESET_BOOST:
        if (!turbo_mode_) {
          send_turbo_command(true);
          turbo_mode_ = true;
          eco_mode_ = false;
          quiet_mode_ = false;
          needs_update = true;
        }
        break;
        
      case climate::CLIMATE_PRESET_SLEEP:
        if (sleep_mode_ == SLEEP_OFF) {
          send_sleep_command(SLEEP_1);
          sleep_mode_ = SLEEP_1;
          needs_update = true;
        }
        break;
        
      case climate::CLIMATE_PRESET_NONE:
      default:
        if (eco_mode_ || turbo_mode_ || sleep_mode_ != SLEEP_OFF) {
          if (eco_mode_) send_eco_command(false);
          if (turbo_mode_) send_turbo_command(false);
          if (sleep_mode_ != SLEEP_OFF) send_sleep_command(SLEEP_OFF);
          eco_mode_ = false;
          turbo_mode_ = false;
          sleep_mode_ = SLEEP_OFF;
          needs_update = true;
        }
        break;
    }
    
    this->preset = preset;
  }
  
  if (needs_update) {
    this->publish_state();
  }
}

void HisenseClimate::send_command(const std::vector<uint8_t> &command) {
  tx_queue_.push(command);
}

void HisenseClimate::send_power_command(bool on) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 
    static_cast<uint8_t>(on ? 0x0C : 0x04), // Power byte
    0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  // Calculate checksum
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_mode_command(ACMode mode) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00,
    static_cast<uint8_t>(0x0C | (mode << 4)), // Mode + power on
    0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_temperature_command(uint8_t temp) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00,
    static_cast<uint8_t>((temp << 1) | 0x01), // Temperature encoding
    0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_fan_command(FanSpeed speed) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 
    static_cast<uint8_t>(speed), // Fan speed
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_swing_command(bool vertical, bool horizontal) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    static_cast<uint8_t>((vertical ? 0x80 : 0x00) | (horizontal ? 0x40 : 0x00)), // Swing byte
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_turbo_command(bool on) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    static_cast<uint8_t>(on ? 0x02 : 0x00), // Turbo byte
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_eco_command(bool on) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    static_cast<uint8_t>(on ? 0x04 : 0x00), // Eco byte
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_quiet_command(bool on) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00,
    static_cast<uint8_t>(on ? 0x04 : 0x00), // Quiet byte
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_led_command(bool on) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00,
    static_cast<uint8_t>(on ? 0x80 : 0x00), // LED byte
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::send_sleep_command(SleepMode mode) {
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x65, 0x00, 0x00, 0x00,
    static_cast<uint8_t>(mode), // Sleep mode
    0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xF4, 0xFB
  };
  
  uint16_t checksum = calculate_checksum(cmd.data(), 2, cmd.size() - 4);
  cmd[cmd.size() - 4] = (checksum >> 8) & 0xFF;
  cmd[cmd.size() - 3] = checksum & 0xFF;
  
  send_command(cmd);
}

void HisenseClimate::query_status() {
  ESP_LOGV(TAG, "Sending status query command");
  std::vector<uint8_t> cmd = {
    0xF4, 0xF5, 0x00, 0x40, 0x0C, 0x00, 0x00, 0x01, 0x01, 0xFE, 0x01,
    0x00, 0x00, 0x66, 0x00, 0x00, 0x00, 0x01, 0xB3, 0xF4, 0xFB
  };
  
  send_command(cmd);
}

bool HisenseClimate::parse_frame(const uint8_t *data, size_t len) {
  // Validate frame structure
  if (len < sizeof(DeviceStatus)) {
    return false;
  }
  
  if (data[0] != FRAME_HEADER_1 || data[1] != FRAME_HEADER_2) {
    return false;
  }
  
  if (data[len - 2] != FRAME_FOOTER_1 || data[len - 1] != FRAME_FOOTER_2) {
    return false;
  }
  
  // Verify checksum
  uint16_t calc_checksum = calculate_checksum(data, 2, len - 4);
  uint16_t recv_checksum = (data[len - 4] << 8) | data[len - 3];
  
  if (calc_checksum != recv_checksum) {
    ESP_LOGW(TAG, "Checksum mismatch: calc=%04X recv=%04X", calc_checksum, recv_checksum);
    return false;
  }
  
  // Process status if this is a status response
  if (data[2] == MSG_TYPE_RESPONSE) {
    process_status(reinterpret_cast<const DeviceStatus*>(data));
  }
  
  return true;
}

uint16_t HisenseClimate::calculate_checksum(const uint8_t *data, size_t start, size_t end) {
  uint16_t sum = 0;
  for (size_t i = start; i < end; i++) {
    sum += data[i];
  }
  return sum;
}

void HisenseClimate::process_status(const DeviceStatus *status) {
  ESP_LOGD(TAG, "Processing status update");
  
  // Extract power state
  bool power = (status->mode_and_power & 0x08) != 0;
  power_state_ = power;
  ESP_LOGV(TAG, "Power state: %s", power ? "ON" : "OFF");
  
  // Extract mode
  uint8_t mode_bits = (status->mode_and_power >> 4) & 0x0F;
  current_mode_ = static_cast<ACMode>(mode_bits);
  ESP_LOGV(TAG, "Mode: %d", current_mode_);
  
  // Update climate mode
  if (!power) {
    this->mode = climate::CLIMATE_MODE_OFF;
    this->action = climate::CLIMATE_ACTION_OFF;
  } else {
    this->mode = ac_mode_to_climate_mode(current_mode_);
    
    // Determine action based on mode and compressor
    bool compressor_running = status->compressor_frequency > 0;
    
    switch (current_mode_) {
      case MODE_COOL:
        this->action = compressor_running ? 
          climate::CLIMATE_ACTION_COOLING : climate::CLIMATE_ACTION_IDLE;
        break;
      case MODE_HEAT:
        this->action = compressor_running ? 
          climate::CLIMATE_ACTION_HEATING : climate::CLIMATE_ACTION_IDLE;
        break;
      case MODE_DRY:
        this->action = compressor_running ? 
          climate::CLIMATE_ACTION_DRYING : climate::CLIMATE_ACTION_IDLE;
        break;
      case MODE_FAN_ONLY:
        this->action = climate::CLIMATE_ACTION_FAN;
        break;
      default:
        this->action = climate::CLIMATE_ACTION_IDLE;
        break;
    }
  }
  
  // Update temperatures
  target_temperature_ = status->temperature_setting;
  current_temperature_ = status->temperature_current;
  this->target_temperature = target_temperature_;
  this->current_temperature = current_temperature_;
  
  // Update fan mode
  fan_speed_ = static_cast<FanSpeed>(status->wind_status);
  this->fan_mode = fan_speed_to_climate_fan(fan_speed_);
  
  // Update swing modes
  swing_vertical_ = (status->swing_status & 0x80) != 0;
  swing_horizontal_ = (status->swing_status & 0x40) != 0;
  
  if (swing_vertical_ && swing_horizontal_) {
    this->swing_mode = climate::CLIMATE_SWING_BOTH;
  } else if (swing_vertical_) {
    this->swing_mode = climate::CLIMATE_SWING_VERTICAL;
  } else if (swing_horizontal_) {
    this->swing_mode = climate::CLIMATE_SWING_HORIZONTAL;
  } else {
    this->swing_mode = climate::CLIMATE_SWING_OFF;
  }
  
  // Update special modes
  turbo_mode_ = (status->turbo_eco_status & 0x02) != 0;
  eco_mode_ = (status->turbo_eco_status & 0x04) != 0;
  quiet_mode_ = (status->quiet_status & 0x04) != 0;
  led_enabled_ = (status->led_status & 0x80) != 0;
  
  // Update preset
  if (turbo_mode_) {
    this->preset = climate::CLIMATE_PRESET_BOOST;
  } else if (eco_mode_) {
    this->preset = climate::CLIMATE_PRESET_ECO;
  } else if (status->sleep_status > 0) {
    this->preset = climate::CLIMATE_PRESET_SLEEP;
  } else {
    this->preset = climate::CLIMATE_PRESET_NONE;
  }
  
  // Update sensors
  update_sensor(compressor_frequency_sensor_, status->compressor_frequency);
  update_sensor(outdoor_temperature_sensor_, status->outdoor_temperature);
  update_sensor(pipe_temperature_sensor_, status->pipe_temperature);
  
  ESP_LOGD(TAG, "Status update complete - Temp: %.0f/%.0f°C, Mode: %d, Power: %s",
           current_temperature_, target_temperature_, current_mode_,
           power_state_ ? "ON" : "OFF");
  
  // Publish state
  this->publish_state();
}

climate::ClimateMode HisenseClimate::ac_mode_to_climate_mode(ACMode mode) {
  switch (mode) {
    case MODE_COOL:
      return climate::CLIMATE_MODE_COOL;
    case MODE_HEAT:
      return climate::CLIMATE_MODE_HEAT;
    case MODE_DRY:
      return climate::CLIMATE_MODE_DRY;
    case MODE_FAN_ONLY:
      return climate::CLIMATE_MODE_FAN_ONLY;
    case MODE_AUTO:
      return climate::CLIMATE_MODE_HEAT_COOL;
    default:
      return climate::CLIMATE_MODE_OFF;
  }
}

ACMode HisenseClimate::climate_mode_to_ac_mode(climate::ClimateMode mode) {
  switch (mode) {
    case climate::CLIMATE_MODE_COOL:
      return MODE_COOL;
    case climate::CLIMATE_MODE_HEAT:
      return MODE_HEAT;
    case climate::CLIMATE_MODE_DRY:
      return MODE_DRY;
    case climate::CLIMATE_MODE_FAN_ONLY:
      return MODE_FAN_ONLY;
    case climate::CLIMATE_MODE_HEAT_COOL:
      return MODE_AUTO;
    default:
      return MODE_COOL;
  }
}

climate::ClimateFanMode HisenseClimate::fan_speed_to_climate_fan(FanSpeed speed) {
  switch (speed) {
    case FAN_AUTO:
      return climate::CLIMATE_FAN_AUTO;
    case FAN_QUIET:
      return climate::CLIMATE_FAN_QUIET;
    case FAN_LOW:
      return climate::CLIMATE_FAN_LOW;
    case FAN_MEDIUM:
      return climate::CLIMATE_FAN_MEDIUM;
    case FAN_HIGH:
    case FAN_TURBO:
      return climate::CLIMATE_FAN_HIGH;
    default:
      return climate::CLIMATE_FAN_AUTO;
  }
}

FanSpeed HisenseClimate::climate_fan_to_fan_speed(climate::ClimateFanMode fan) {
  switch (fan) {
    case climate::CLIMATE_FAN_AUTO:
      return FAN_AUTO;
    case climate::CLIMATE_FAN_QUIET:
      return FAN_QUIET;
    case climate::CLIMATE_FAN_LOW:
      return FAN_LOW;
    case climate::CLIMATE_FAN_MEDIUM:
      return FAN_MEDIUM;
    case climate::CLIMATE_FAN_HIGH:
      return FAN_HIGH;
    default:
      return FAN_AUTO;
  }
}

void HisenseClimate::update_sensor(sensor::Sensor *sensor, float value) {
  if (sensor != nullptr && (!sensor->has_state() || sensor->get_raw_state() != value)) {
    sensor->publish_state(value);
  }
}

}  // namespace hisense_ac
}  // namespace esphome