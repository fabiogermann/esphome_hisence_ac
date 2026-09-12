#include "air_conditioner.h"
#include "esphome/core/helpers.h"
#include "esphome/core/log.h"
#include <cmath>
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

  // Comm-watchdog: if no bytes have arrived for a while AND we haven't just
  // changed status, treat the link as dead and back off. We intentionally do
  // NOT clear rx_buffer_ here - the resync-safe extractor in try_extract_frame_
  // discards garbage on its own, and clearing here can throw away a partially
  // received frame.
  //
  // CRITICAL: skip the watchdog while we are already in after_fail. The
  // after_fail block has its own backoff timer; letting the watchdog re-fire
  // inside that wait window stacks state changes, reshuffles last_status_change
  // and prevents the retry from ever actually firing.
  if (status != Status::after_fail &&
      millis() - this->last_recived_ > COMM_TIMEOUT_MS &&
      millis() - this->last_status_change > COMM_TIMEOUT_MS) {
    ESP_LOGD(TAG, "Communication timeout - resetting (errors: %u)",
             static_cast<unsigned>(this->consecutive_errors_));
    if (this->consecutive_errors_ < 0xFF) {
      this->consecutive_errors_++;
    }
    change_status(Status::after_fail);
    return;
  }

  if (status == Status::after_fail) {
    // Flush any pending hardware bytes so the next retry starts clean. We do
    // not touch rx_buffer_; if a real frame is mid-flight in there, the
    // extractor will pick it up after the backoff.
    uint8_t byte;
    while (available() && read_byte(&byte)) {
      // intentional drain
    }
    flush();

    auto time_since_fail = millis() - last_status_change;
    // Exponential-ish backoff capped at 10s. Many Hisense indoor units go
    // semi-dormant when the AC is OFF and ignore queries for tens of seconds.
    uint32_t retry_delay = RETRY_DELAY_BASE_MS;
    if (consecutive_errors_ > 2) retry_delay = 4000;
    if (consecutive_errors_ > 5) retry_delay = 7000;
    if (consecutive_errors_ > 8) retry_delay = 10000;

    if (time_since_fail < retry_delay) {
      if (print_extra_log_in_this_loop)
        ESP_LOGD(TAG, "Waiting %u ms before retry (errors: %u)",
                 static_cast<unsigned>(retry_delay - time_since_fail),
                 static_cast<unsigned>(consecutive_errors_));
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

  if (millis() - this->last_recived_ > QUERY_PERIOD_MS &&
      status == Status::standby) {
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
  size_t bytes_this_loop = 0;
  while ((available_to_read = this->available()) > 0) {
    int chunk_size = std::min(available_to_read, 64);
    std::vector<uint8_t> rec_buffer;
    rec_buffer.resize(chunk_size, 0);

    this->read_array(&rec_buffer[0], chunk_size);
    this->rx_buffer_.insert(this->rx_buffer_.end(), rec_buffer.begin(),
                            rec_buffer.end());
    this->last_recived_ = millis();
    this->total_bytes_received_ += chunk_size;
    bytes_this_loop += chunk_size;

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
      ESP_LOGV(TAG, "Parsing OK message: %s (%u)",
               format_hex_pretty(payload).c_str(),
               static_cast<unsigned>(payload.size()));
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

  // Diagnostic: if we received bytes but no complete frame closed, surface
  // that periodically so it's clear the wire is alive even when frames aren't.
  if (bytes_this_loop > 0 && print_extra_log_in_this_loop) {
    ESP_LOGD(TAG, "Got %u byte(s) this loop, no frame yet (rx_buf: %u)",
             static_cast<unsigned>(bytes_this_loop),
             static_cast<unsigned>(this->rx_buffer_.size()));
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

  // ---------------------------------------------------------------------
  // Build a 50-byte command frame.
  //
  // Mode and power are packed into the SINGLE byte status[18]; there is no
  // separate command discriminator or "envelope":
  //
  //   status[18] = ((encode_mode << 1) | 1) << 4 | 0x0C   (power on + mode)
  //   status[18] = 0x04                                    (OFF sentinel)
  //   status[18] = 0x00                                    (temp-only)
  //
  //   with encode_mode: FAN_ONLY=0, HEAT=1, COOL=2, DRY=3, AUTO=4, giving
  //   the on-wire bytes 0x1C / 0x3C / 0x5C / 0x7C / 0x9C.
  //
  // The low nibble 0x0C (bits 2+3) is what asserts power-on; without it the
  // AC shifts its mode register but never starts the compressor.
  //
  // REGRESSION NOTE: an earlier rewrite (c1609e9) used the historical
  // mode-change-while-on frames (status[16]=0x01, status[17]=0x01,
  // status[18]=mode<<4 plus a status[31..35] envelope 10 01 04 00 10).
  // Those frames are ACKed (one beep) but never assert the power bit, so
  // power-on from Home Assistant silently stopped working. The single-byte
  // 0x?C encoding above is what actually powers the unit on from standby
  // (verified on real hardware, see docs/PROTOCOL.md and
  // tests/test_command_frames.py).
  //
  //   status[19] = (target << 1) | 1   (°C, or °F when use_fahrenheit_)
  // ---------------------------------------------------------------------

  std::vector<uint8_t> status{
      0xF4, 0xF5, 0x00, 0x40, 0x29, 0x00, 0x00, 0x01, 0x01, 0xFE,
      0x01, 0x00, 0x00, 0x65, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
      0x00, 0x00, 0x00, 0x00, 0x00, 0x00};

  // -----------------------------------------------------------------
  // Mode change (also carries the power bits)
  // -----------------------------------------------------------------
  if (next_hvac_settings.mode != nullopt) {
    const auto requested_mode = next_hvac_settings.mode.value();

    if (requested_mode == climate::CLIMATE_MODE_OFF) {
      // OFF sentinel. Everything else in the frame stays zero.
      status[18] = 0x04;
    } else {
      uint8_t encode_mode = 0;
      switch (requested_mode) {
      case climate::CLIMATE_MODE_FAN_ONLY:
        encode_mode = 0;
        break;
      case climate::CLIMATE_MODE_HEAT:
        encode_mode = 1;
        break;
      case climate::CLIMATE_MODE_COOL:
        encode_mode = 2;
        break;
      case climate::CLIMATE_MODE_DRY:
        encode_mode = 3;
        break;
      case climate::CLIMATE_MODE_AUTO:
      case climate::CLIMATE_MODE_HEAT_COOL:
        encode_mode = 4;
        break;
      default:
        ESP_LOGW(TAG, "Unsupported climate mode requested: %d",
                 static_cast<int>(requested_mode));
        this->next_hvac_settings_ = nullopt;
        return;
      }
      // Mode + power-on bits packed into one byte (see header comment).
      status[18] = static_cast<uint8_t>((((encode_mode << 1) | 1) << 4) | 0x0C);

      // Mode-only call from HA carries no target temperature. Re-use the
      // current setpoint, falling back to a safe default if it has never
      // been set (NaN on first call after boot would otherwise produce
      // status[19] = 0x01 = 0 C and the AC would reject the frame).
      if (next_hvac_settings.target_temperature == nullopt) {
        if (std::isfinite(this->target_temperature) &&
            this->target_temperature >= 16.0f &&
            this->target_temperature <= 30.0f) {
          next_hvac_settings.target_temperature = this->target_temperature;
        } else {
          next_hvac_settings.target_temperature = 22.0f;
        }
      }
    }
  }

  // -----------------------------------------------------------------
  // Target temperature
  // -----------------------------------------------------------------
  if (next_hvac_settings.target_temperature != nullopt) {
    const float requested = next_hvac_settings.target_temperature.value();
    if (!std::isfinite(requested) || requested < 16.0f || requested > 30.0f) {
      ESP_LOGW(TAG, "Refusing to send out-of-range target temperature %.1f",
               requested);
      // Clear pending so the loop does not re-enter send_status() endlessly.
      this->next_hvac_settings_ = nullopt;
      return;
    }
    // AEH-W4A1 units come in two variants: most speak Celsius natively,
    // some (US-market) expect Fahrenheit on the wire. See PR #11 upstream
    // (pslawinski/esphome_airconintl). HA always works in °C, so convert
    // on the way out when the Fahrenheit variant is configured.
    uint8_t wire_temp;
    if (this->use_fahrenheit_) {
      wire_temp = static_cast<uint8_t>(
          std::lround(requested * 9.0f / 5.0f + 32.0f));
    } else {
      wire_temp = static_cast<uint8_t>(requested);
    }
    status[19] = static_cast<uint8_t>((wire_temp << 1) | 0x01);
  }

  // -----------------------------------------------------------------
  // Swing mode (optional add-on on the same frame)
  // -----------------------------------------------------------------
  if (next_hvac_settings.swing_mode != nullopt) {
    auto next_swing_setting = next_hvac_settings.swing_mode.value();
    switch (next_swing_setting) {
    case climate::CLIMATE_SWING_BOTH:
      status[32] = 0xF0;
      break;
    case climate::CLIMATE_SWING_OFF:
      status[32] = 0x50;
      break;
    case climate::CLIMATE_SWING_VERTICAL:
      status[32] = 0x30;
      break;
    case climate::CLIMATE_SWING_HORIZONTAL:
      status[32] = 0x70;
      break;
    default:
      break;
    }
  }

  // -----------------------------------------------------------------
  // Display LED (status[36])
  // -----------------------------------------------------------------
  status[36] = display_enable ? 0b11000000 : 0b01000000;

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
    // Helper lambda: try to validate a frame ending at the given footer index.
    // Returns true and populates payload_out / consumes bytes if it validates.
    auto try_validate_at = [this, &payload_out](size_t f) -> bool {
      if (f < 4) return false;
      uint32_t s = 0;
      for (size_t i = 2; i + 2 < f; i++) s += this->rx_buffer_[i];
      s &= 0xFFFF;
      const uint8_t hi = (s >> 8) & 0xFF;
      const uint8_t lo = s & 0xFF;
      if (hi != this->rx_buffer_[f - 2] ||
          lo != this->rx_buffer_[f - 1]) {
        return false;
      }
      payload_out.assign(this->rx_buffer_.begin() + 2,
                         this->rx_buffer_.begin() + (f - 2));
      this->rx_buffer_.erase(this->rx_buffer_.begin(),
                             this->rx_buffer_.begin() + f + 2);
      return true;
    };

    if (try_validate_at(footer_idx)) {
      return true;
    }

    // 3a) Doubled-F4 recovery. Some AC firmwares occasionally emit an extra
    // 0xF4 byte just before the footer, yielding ... F4 F4 FB on the wire.
    // If the byte preceding the F4 of the footer is also F4, treat it as a
    // duplicate and retry with footer shifted back by one.
    if (footer_idx >= 3 && this->rx_buffer_[footer_idx - 1] == 0xF4) {
      // Layout: ... [cs_hi] [cs_lo] [F4] [F4] [FB]
      // Original footer_idx points at the first F4 of "F4 FB". If we move
      // it back by 1, the new footer pair is (F4, FB at idx footer_idx,
      // footer_idx+1) -- wait, that's the same. We instead need to drop one
      // F4 byte from the buffer and revalidate at the same logical end.
      // Easiest: erase the byte at (footer_idx-1) and let the loop retry.
      ESP_LOGV(TAG, "Doubled-F4 detected before footer - retrying");
      this->rx_buffer_.erase(this->rx_buffer_.begin() + (footer_idx - 1));
      // After erase, the F4 FB pair is now at (footer_idx-1, footer_idx).
      if (try_validate_at(footer_idx - 1)) {
        return true;
      }
    }

    // Real checksum failure. Log and resync past this header.
    const uint32_t sum_now = [this, footer_idx]() {
      uint32_t s = 0;
      for (size_t i = 2; i + 2 < footer_idx; i++) s += this->rx_buffer_[i];
      return s & 0xFFFF;
    }();
    const uint8_t expected_hi = (sum_now >> 8) & 0xFF;
    const uint8_t expected_lo = sum_now & 0xFF;
    const uint8_t provided_hi = this->rx_buffer_[footer_idx - 2];
    const uint8_t provided_lo = this->rx_buffer_[footer_idx - 1];
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
  return false;
}

void AirConditioner::dump_config() {
  ESP_LOGCONFIG(TAG, "Hisense:");
  LOG_PIN("  Flow Control Pin: ", this->flow_control_pin_);
  ESP_LOGCONFIG(TAG, "  Checksum errors: %d", this->checksum_error_count_);
}

void AirConditioner::send_raw(const std::vector<uint8_t> &payload) {
  // payload includes the leading F4 F5 header; checksum and F4 FB footer
  // are appended here.
  if (payload.empty()) {
    return;
  }
  auto const checksum = this->checksum(payload);
  uint8_t cr1 = (checksum & 0x0000ff00) >> 8;
  uint8_t cr2 = (checksum & 0x000000ff);

  if (this->flow_control_pin_ != nullptr)
    this->flow_control_pin_->digital_write(true);

  // Byte-stuffing on TX: every literal 0xF4 inside the body AND inside the
  // two checksum bytes is transmitted as F4 F4 (adopted from upstream
  // pslawinski messages.h, whose on-wire templates pre-stuff - e.g.
  // temp_16_C's 0x01F4 checksum goes out as 01 F4 F4 F4 FB). The AC
  // de-stuffs on receive; without this a frame like a 16 °C setpoint
  // (checksum low byte 0xF4) collides with the F4 FB footer marker.
  // Header F4 F5 and footer F4 FB are sent unstuffed.
  this->write_byte(0xF4);
  this->write_byte(0xF5);
  for (size_t i = 2; i < payload.size(); i++) {
    this->write_byte(payload[i]);
    if (payload[i] == 0xF4) {
      this->write_byte(0xF4);
    }
  }
  this->write_byte(cr1);
  if (cr1 == 0xF4) {
    this->write_byte(0xF4);
  }
  this->write_byte(cr2);
  if (cr2 == 0xF4) {
    this->write_byte(0xF4);
  }
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
  ESP_LOGV(TAG, "decode_message");

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
      ESP_LOGV(TAG, "mode %d", z);
    } else {
      ESP_LOGV(TAG, "Seem to be OFF.");
      this->mode = climate::CLIMATE_MODE_OFF;
    }
  }

  // Target temp
  {
    auto temp = payload[17];
    // Fahrenheit-variant units report °F on the wire (upstream PR #11);
    // HA works in °C, so convert on the way in.
    this->target_temperature = this->use_fahrenheit_
                                   ? (temp - 32.0f) * 5.0f / 9.0f
                                   : static_cast<float>(temp);
  }

  // Fan speed
  {
    auto wind = decode_wind_codes[payload[14]];
    this->fan_mode = wind;
    ESP_LOGV(TAG, "fan speed %d", wind);
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
  ESP_LOGV(TAG, "acc status new");
  this->publish_state();

#ifdef USE_SENSOR
  {
    // Fahrenheit-variant units report all temperatures as °F (upstream
    // PR #11); convert to °C for HA when configured.
    auto wire_to_c = [this](uint8_t v) -> float {
      return this->use_fahrenheit_ ? (v - 32.0f) * 5.0f / 9.0f
                                   : static_cast<float>(v);
    };
    update_sub_sensor_(SubSensorType::INDOOR_TEMPERATURE,
                       wire_to_c(payload[18]));
    update_sub_sensor_(SubSensorType::INDOOR_COIL_TEMPERATURE,
                       wire_to_c(payload[19]));
    // NOTE: payload[21] is always 0x80 on observed Hisense status frames;
    // it is a flag byte, not humidity. Indoor humidity is not exposed by
    // this protocol. The INDOOR_HUMIDITY sub-sensor has been removed.
    // Outdoor temperatures live in the body[42..45] block on observed
    // 76-byte status payloads (40/41 are zeros).
    update_sub_sensor_(SubSensorType::OUTDOOR_TEMPERATURE,
                       wire_to_c(payload[42]));
    update_sub_sensor_(SubSensorType::OUTDOOR_COIL_TEMPERATURE,
                       wire_to_c(payload[43]));
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
  // Idempotent: don't churn last_status_change when the state didn't change.
  // Other timers (notably the after_fail backoff and the comm watchdog) read
  // last_status_change to gate their own decisions; resetting it on a no-op
  // call breaks those timers.
  if (this->status == new_status) {
    return;
  }
  this->status = new_status;
  last_status_change = millis();
}

} // namespace ac
} // namespace hisense
} // namespace esphome