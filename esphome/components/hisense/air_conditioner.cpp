#include "air_conditioner.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
namespace esphome {
namespace hisense {
namespace ac {
static const char *const TAG = "climate.air_conditioner";

void AirConditioner::setup() {
  if (this->flow_control_pin_ != nullptr) {
    this->flow_control_pin_->setup();
  }
  this->last_status_change = millis();
  this->status = Status::standby;
  this->checksum_error_count_ = 0;
  this->consecutive_errors_ = 0;
}
void AirConditioner::loop() {
  if (millis() - this->last_extra_log_print > 3000) {
    print_extra_log_in_this_loop = true;
    this->last_extra_log_print = millis();
  } else {
    print_extra_log_in_this_loop = false;
  }

  if (millis() - this->last_recived_ > 8000 &&
      millis() - this->last_status_change > 8000) {
    ESP_LOGD(TAG, "Communication timeout - resetting");
    this->rx_buffer_.clear();
    this->consecutive_errors_ = 0;
    change_status(Status::after_fail);
    return;
  }

  if (status == Status::after_fail) {
    this->rx_buffer_.clear();
    uint8_t byte;
    while (available() && read_byte(&byte)) {
      // Flush any remaining bytes
    }
    flush();

    auto time_since_fail = millis() - last_status_change;
    auto retry_delay = (consecutive_errors_ > 3) ? 4000 : 2000;

    if (time_since_fail < retry_delay) {
      if (print_extra_log_in_this_loop)
        ESP_LOGD(TAG, "Waiting %d ms before retry (errors: %d)",
                 retry_delay - time_since_fail, consecutive_errors_);
      return;
    }

    ESP_LOGD(TAG, "Retrying communication");
    change_status(Status::standby);
    return;
  }

  if (this->next_hvac_settings_) {
    send_status();
    change_status(Status::waiting_for_change_confirm);
    return;
  }

  if (millis() - this->last_recived_ > 2000 && status == Status::standby) {
    ESP_LOGD(TAG, "Requesting status");
    std::vector<uint8_t> requst_status{0xF4, 0xF5, 0x00, 0x40, 0x0C, 0x00,
                                       0x00, 0x01, 0x01, 0xFE, 0x01, 0x00,
                                       0x00, 0x66, 0x00, 0x00, 0x00};
    this->send_raw(requst_status);
    // F4 F5 00 40 0C 00 00 01 01 FE 01 00 00 66 00 00 00 01 B3 F4 FB
    change_status(Status::waiting_for_status_response);

    return;
  }

  int available_to_read = 0;
  bool any_frame_decoded = false;
  while ((available_to_read = this->available()) > 0) {
    int chunk_size = std::min(available_to_read, 64);
    std::vector<uint8_t> rec_buffer;
    rec_buffer.resize(chunk_size, 0);

    this->read_array(&rec_buffer[0], chunk_size);
    this->rx_buffer_.insert(this->rx_buffer_.end(), rec_buffer.begin(),
                            rec_buffer.end());
    this->last_recived_ = millis();

    // Hard cap on backlog. The streaming extractor self-resyncs over garbage,
    // but we still need a ceiling so a continuously-noisy line can't grow the
    // buffer unboundedly. Keep the last MAX_FRAME_SIZE bytes so any partial
    // frame in progress survives the trim.
    if (this->rx_buffer_.size() > 4 * MAX_FRAME_SIZE) {
      ESP_LOGW(TAG, "RX buffer high-water mark - trimming");
      this->rx_buffer_.erase(this->rx_buffer_.begin(),
                             this->rx_buffer_.end() - MAX_FRAME_SIZE);
    }

    // Drain every complete frame that arrived in this chunk. Each successful
    // extraction removes its bytes (plus any leading garbage) from rx_buffer_.
    std::vector<uint8_t> payload;
    while (this->try_extract_frame_(payload)) {
      ESP_LOGD(TAG, "Parsing OK message: %s (%d)",
               format_hex_pretty(payload).c_str(), payload.size());
      this->decode_message(payload);
      any_frame_decoded = true;
      this->consecutive_errors_ = 0;
      if (this->waiting_for_response) {
        this->waiting_for_response = 0;
      }
      payload.clear();
    }
  }

  if (any_frame_decoded) {
    change_status(Status::standby);
    return;
  }
}

float AirConditioner::get_setup_priority() const {
  // After UART bus
  return setup_priority::BUS - 1.0f;
}

climate::ClimateTraits AirConditioner::traits() {
  auto traits = climate::ClimateTraits();

  traits.set_supported_modes(
      {climate::CLIMATE_MODE_OFF, climate::CLIMATE_MODE_COOL,
       climate::CLIMATE_MODE_HEAT, climate::CLIMATE_MODE_FAN_ONLY,
       climate::CLIMATE_MODE_DRY, climate::CLIMATE_MODE_HEAT_COOL});

  traits.set_supported_fan_modes(
      {climate::CLIMATE_FAN_OFF, climate::CLIMATE_FAN_AUTO,
       climate::CLIMATE_FAN_LOW, climate::CLIMATE_FAN_FOCUS,
       climate::CLIMATE_FAN_MEDIUM, climate::CLIMATE_FAN_MIDDLE,
       climate::CLIMATE_FAN_HIGH});

  traits.set_supported_swing_modes(
      {climate::CLIMATE_SWING_OFF, climate::CLIMATE_SWING_BOTH,
       climate::CLIMATE_SWING_VERTICAL, climate::CLIMATE_SWING_HORIZONTAL});

  traits.add_feature_flags(climate::CLIMATE_SUPPORTS_CURRENT_TEMPERATURE);
  traits.set_visual_target_temperature_step(1.0f);

  return traits;
}
void AirConditioner::send_status() {
  if (this->next_hvac_settings_ == nullopt) {
    ESP_LOGD(TAG, "send_status nullopt");
    return;
  }
  auto next_hvac_settings = next_hvac_settings_.value();

  std::vector<uint8_t> status{
      0xF4,
      0xF5, // 1
      0x00, // 2
      0x40, // 3
      0x29, // 4
      0x00, // 5
      0x00, // 6
      0x01, // 7
      0x01, // 8
      0xFE, // 9
      0x01, // 10
      0x00, // 11
      0x00, // 12
      0x65, // 13
      0x00, // 14
      0x00, // 15
      0x00, // 16
      0x00, // 17
      0x00, // 18
      0x00, // 19
      0x00, // 20
      0x00, // 21
      0x00, // 22
      0x04, // 23
      0x00, // 24
      0x00, // 25
      0x00, // 26
      0x00, // 27
      0x00, // 28
      0x00, // 29
      0x00, // 30
      0x00, // 31
      0x00, // 32
      0x00, // 33
      0x00, // 34
      0x00, // 35
      0x00, // 36
      0x00, // 37
      0x00, // 38
      0x00, // 39
      0x00, // 40
      0x00, // 41
      0x00, // 42
      0x00, // 43
      0x00, // 44
      0x00  // 45
  };

  if (next_hvac_settings.mode != nullopt) {
    int mode = encode_climateMode((next_hvac_settings.mode.value()));

    if (next_hvac_settings.mode.value() == climate::CLIMATE_MODE_OFF) {
      status[18] = 0b00000100;

    } else {
      uint8_t m_mode = mode << 1;
      m_mode |= (1ul << 0);
      m_mode = m_mode << 4;
      m_mode |= 0b00001100; // To on

      status[18] = m_mode;
      next_hvac_settings.target_temperature = this->target_temperature;
    }
  }

  if (next_hvac_settings.target_temperature != nullopt) {
    auto my_tmp =
        static_cast<uint8_t>(next_hvac_settings.target_temperature.value());

    if (my_tmp < 16ul || my_tmp > 30ul) {
      ESP_LOGD(TAG, "Not valid tmp!");
      return;
    }

    uint8_t c = my_tmp;
    uint8_t tempX = 0;
    tempX = (c << 1);
    tempX |= (1ul << 0);
    status[19] = tempX;
  }
  status[36] = 0b01000000;


  if (display_enable) {
    status[36] = 0b11000000;
  } else {
    status[36] = 0b01000000;
  }

  if (next_hvac_settings.swing_mode != nullopt) {
    // TODO: Combine with decoding
    auto next_swing_setting = next_hvac_settings.swing_mode;
    if (next_swing_setting == climate::ClimateSwingMode::CLIMATE_SWING_BOTH) {
      status[32] = 0b11110000;
    } else if (next_swing_setting ==
               climate::ClimateSwingMode::CLIMATE_SWING_OFF) {
      status[32] = 0b01010000;
    } else if (next_swing_setting ==
               climate::ClimateSwingMode::CLIMATE_SWING_VERTICAL) {
      status[32] = 0b00110000;
    } else if (next_swing_setting ==
               climate::ClimateSwingMode::CLIMATE_SWING_HORIZONTAL) {
      status[32] = 0b01110000;
    }
  }

  send_raw(status);
  this->next_hvac_settings_ = nullopt;
  ESP_LOGD(TAG, "send_status");
}

void AirConditioner::control(const climate::ClimateCall &call) {
  auto next_hvac_settings = HvacSettings();

  if (call.get_mode().has_value())
    next_hvac_settings.mode = call.get_mode();
  if (call.get_fan_mode().has_value())
    next_hvac_settings.fan_mode = call.get_fan_mode();
  if (call.get_swing_mode().has_value())
    next_hvac_settings.swing_mode = call.get_swing_mode();
  if (call.get_target_temperature().has_value())
    next_hvac_settings.target_temperature = call.get_target_temperature();
  if (call.get_preset().has_value())
    next_hvac_settings.preset = call.get_preset();

  this->next_hvac_settings_ = std::move(next_hvac_settings);
}

ParseStatus AirConditioner::parse_ac_message_byte_() {
  // Legacy single-shot entry point. The receive loop now uses the streaming
  // extractor try_extract_frame_() directly; this stub is kept so existing
  // call sites still link. It defers to the streaming extractor and reports a
  // result consistent with the old contract.
  std::vector<uint8_t> payload;
  if (this->try_extract_frame_(payload)) {
    this->decode_message(payload);
    if (this->waiting_for_response) {
      this->waiting_for_response = 0;
    }
    return ParseStatus::PARSE_OK;
  }
  return ParseStatus::NOT_FULL;
}

bool AirConditioner::try_extract_frame_(std::vector<uint8_t> &payload_out) {
  // Resync-safe streaming extractor. Walks rx_buffer_ looking for a complete
  // F4 F5 ... F4 FB frame whose checksum validates. Garbage before the next
  // valid header is silently discarded. See tests/protocol.py StreamingParser
  // for the authoritative behavioural spec.
  while (this->rx_buffer_.size() >= 8) {
    // 1) Locate the next F4 F5 header. Drop anything before it.
    size_t header_idx = 0;
    bool found_header = false;
    for (; header_idx + 1 < this->rx_buffer_.size(); header_idx++) {
      if (this->rx_buffer_[header_idx] == 0xF4 &&
          this->rx_buffer_[header_idx + 1] == 0xF5) {
        found_header = true;
        break;
      }
    }
    if (!found_header) {
      // Keep only the trailing byte in case it's the F4 of an upcoming header.
      if (this->rx_buffer_.size() > 1) {
        const uint8_t last = this->rx_buffer_.back();
        this->rx_buffer_.clear();
        if (last == 0xF4) {
          this->rx_buffer_.push_back(last);
        }
      }
      return false;
    }
    if (header_idx > 0) {
      ESP_LOGV(TAG, "Discarding %u pre-header byte(s)",
               static_cast<unsigned>(header_idx));
      this->rx_buffer_.erase(this->rx_buffer_.begin(),
                             this->rx_buffer_.begin() + header_idx);
    }

    // 2) Look for the F4 FB footer after the header.
    //    A frame is at least header(2) + 2-byte body + cs(2) + footer(2) = 8.
    size_t footer_idx = 0;  // index of the 0xF4 in the footer
    bool found_footer = false;
    for (size_t i = 2; i + 1 < this->rx_buffer_.size(); i++) {
      if (this->rx_buffer_[i] == 0xF4 && this->rx_buffer_[i + 1] == 0xFB) {
        footer_idx = i;
        found_footer = true;
        break;
      }
    }

    if (!found_footer) {
      // No complete frame yet. If we're already over the size cap, give up on
      // this candidate header (it's almost certainly noise that happened to
      // start with F4 F5) and rescan starting from the byte after it.
      if (this->rx_buffer_.size() > MAX_FRAME_SIZE) {
        ESP_LOGD(TAG,
                 "No footer within %u bytes - discarding spurious header",
                 static_cast<unsigned>(MAX_FRAME_SIZE));
        this->rx_buffer_.erase(this->rx_buffer_.begin(),
                               this->rx_buffer_.begin() + 1);
        continue;
      }
      return false;  // wait for more bytes
    }

    // 3) Validate checksum. Big-endian 2-byte sum of frame[2 .. footer_idx-2].
    if (footer_idx < 4) {
      // Footer too close to header - impossible frame; drop the header.
      this->rx_buffer_.erase(this->rx_buffer_.begin(),
                             this->rx_buffer_.begin() + 1);
      continue;
    }
    uint32_t sum = 0;
    for (size_t i = 2; i + 2 < footer_idx; i++) {
      sum += this->rx_buffer_[i];
    }
    sum &= 0xFFFF;
    const uint8_t expected_hi = (sum >> 8) & 0xFF;
    const uint8_t expected_lo = sum & 0xFF;
    const uint8_t provided_hi = this->rx_buffer_[footer_idx - 2];
    const uint8_t provided_lo = this->rx_buffer_[footer_idx - 1];

    if (expected_hi != provided_hi || expected_lo != provided_lo) {
      this->checksum_error_count_++;
      ESP_LOGD(TAG,
               "Checksum error #%u - expected 0x%02x 0x%02x, got 0x%02x 0x%02x",
               static_cast<unsigned>(this->checksum_error_count_),
               expected_hi, expected_lo, provided_hi, provided_lo);
      // The closed candidate is bogus. It may still contain an embedded real
      // header further along; advance past just this header so we keep
      // scanning the absorbed bytes.
      this->rx_buffer_.erase(this->rx_buffer_.begin(),
                             this->rx_buffer_.begin() + 1);
      continue;
    }

    // 4) Frame is valid. Extract the body (between header and checksum) and
    //    pop the consumed bytes (including the trailing footer).
    payload_out.assign(this->rx_buffer_.begin() + 2,
                       this->rx_buffer_.begin() + (footer_idx - 2));
    this->rx_buffer_.erase(this->rx_buffer_.begin(),
                           this->rx_buffer_.begin() + footer_idx + 2);
    return true;
  }
  return false;
}

void AirConditioner::dump_config() {
  ESP_LOGCONFIG(TAG, "Hisense:");
  LOG_PIN("  Flow Control Pin: ", this->flow_control_pin_);
  ESP_LOGCONFIG(TAG, "  Checksum errors: %d", this->checksum_error_count_);
}

void AirConditioner::send_raw(const std::vector<uint8_t> &payload) {
  // Add F4 F5 at start

  if (payload.empty()) {
    return;
  }
  auto const checksum = this->checksum(payload);
  uint8_t cr1 = (checksum & 0x0000ff00) >> 8;
  uint8_t cr2 = (checksum & 0x000000ff);

  if (this->flow_control_pin_ != nullptr)
    this->flow_control_pin_->digital_write(true);

  this->write_array(payload);
  this->write_byte(cr1);
  this->write_byte(cr2);
  this->write_byte(0xF4);
  this->write_byte(0xFB);
  this->flush();

  if (this->flow_control_pin_ != nullptr)
    this->flow_control_pin_->digital_write(false);
  waiting_for_response = 1;

  last_send_ = millis();
}

short int AirConditioner::checksum(const std::vector<uint8_t> &payload) {
  short int csum = 0;
  int arrlen = payload.size();
  for (int i = 2; i < arrlen; i++) {
    csum = csum + payload[i];
  }
  return csum;
}

void AirConditioner::decode_message(std::vector<uint8_t> payload) {
  ESP_LOGD(TAG, "decode_message");

  static optional<climate::ClimateFanMode> decode_wind_codes[19]{
      climate::ClimateFanMode::CLIMATE_FAN_OFF,
      climate::ClimateFanMode::CLIMATE_FAN_AUTO,
      climate::ClimateFanMode::CLIMATE_FAN_AUTO,
      nullopt,
      nullopt,
      nullopt,
      nullopt,
      nullopt,
      nullopt,
      nullopt,
      climate::ClimateFanMode::CLIMATE_FAN_LOW, //"1",
      nullopt,
      climate::ClimateFanMode::CLIMATE_FAN_FOCUS, //"2",
      nullopt,
      climate::ClimateFanMode::CLIMATE_FAN_MEDIUM, //"3",
      nullopt,
      climate::ClimateFanMode::CLIMATE_FAN_MIDDLE, //"4",
      nullopt,
      climate::ClimateFanMode::CLIMATE_FAN_HIGH, //"5"
  };

  // Is ON
  {
    uint8_t mask = 0b00001000;
    bool is_on = ((payload[16] & mask) != 0);
    if (is_on) {
      auto z = decode_climateMode((payload[16] >> 4));
      this->mode = z;
      ESP_LOGD(TAG, "mode %d", z);
    } else {
      ESP_LOGD(TAG, "Seem to be OFF.");
      this->mode = climate::CLIMATE_MODE_OFF;
    }
  }

  // Target temp
  {
    auto temp = payload[17];
    this->target_temperature = temp;
  }

  // Fan speed
  {
    auto wind = decode_wind_codes[payload[14]];
    this->fan_mode = wind;
    ESP_LOGD(TAG, "fan speed %d", wind);
  }

  // Swig detect
  {
    uint8_t updown_mask = 0b01000000;
    bool up_down = (payload[33] & updown_mask) != 0;

    uint8_t lr_mask = 0b10000000;
    bool left_right = (payload[33] & lr_mask) != 0;

    if (left_right && up_down) {
      swing_mode = climate::ClimateSwingMode::CLIMATE_SWING_BOTH;
    } else if (left_right) {
      swing_mode = climate::ClimateSwingMode::CLIMATE_SWING_VERTICAL;
    } else if (up_down) {
      swing_mode = climate::ClimateSwingMode::CLIMATE_SWING_HORIZONTAL;
    } else {
      swing_mode = climate::ClimateSwingMode::CLIMATE_SWING_OFF;
    }
  }
  ESP_LOGD(TAG, "acc status new");
  this->publish_state();

#ifdef USE_SENSOR
  {
    update_sub_sensor_(SubSensorType::INDOOR_TEMPERATURE,
                       static_cast<float>(payload[18]));
    update_sub_sensor_(SubSensorType::INDOOR_COIL_TEMPERATURE,
                       static_cast<float>(payload[19]));

    update_sub_sensor_(SubSensorType::INDOOR_HUMIDITY,
                       static_cast<float>(payload[21]));
    update_sub_sensor_(SubSensorType::OUTDOOR_TEMPERATURE,
                       static_cast<float>(payload[40]));
    update_sub_sensor_(SubSensorType::OUTDOOR_COIL_TEMPERATURE,
                       static_cast<float>(payload[41]));

    //  update_sub_sensor_(SubSensorType::OUTDOOR_TEMPERATURE,
    //  static_cast<float>(payload[41])); //OutDoor coil?
  }
#endif

}

#ifdef USE_SENSOR
void AirConditioner::set_sub_sensor(SubSensorType type, sensor::Sensor *sens) {
  std::size_t index = static_cast<std::size_t>(type);
  if (index < sub_sensors_.size()) {
    sub_sensors_[index] = sens;
  } else {
    ESP_LOGE(TAG, "Not valid sensor index: %d", index);
  }
};
void AirConditioner::update_sub_sensor_(SubSensorType type, float value) {
  std::size_t index = static_cast<std::size_t>(type);
  if (index < sub_sensors_.size() && sub_sensors_[index] != nullptr) {
    sub_sensors_[index]->publish_state(value);
  } else {
    ESP_LOGE(TAG, "Not valid sensor index: %d", index);
  }
};
#endif

void AirConditioner::set_display_switch(bool state) {
  auto next_hvac_settings = HvacSettings();
  next_hvac_settings.display = state;
  this->next_hvac_settings_ = std::move(next_hvac_settings);
  display_enable = state;
}

void AirConditioner::change_status(Status new_status) {
  this->status = new_status;
  last_status_change = millis();
}

} // namespace ac
} // namespace hisense
} // namespace esphome