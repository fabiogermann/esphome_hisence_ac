#pragma once

#include "esphome/core/component.h"
#include "esphome/components/climate/climate.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/sensor/sensor.h"
#include <vector>
#include <queue>

namespace esphome {
namespace hisense_ac {

// Protocol constants
static const uint8_t FRAME_HEADER_1 = 0xF4;
static const uint8_t FRAME_HEADER_2 = 0xF5;
static const uint8_t FRAME_FOOTER_1 = 0xF4;
static const uint8_t FRAME_FOOTER_2 = 0xFB;

static const uint8_t MSG_TYPE_QUERY = 0x66;
static const uint8_t MSG_TYPE_COMMAND = 0x65;
static const uint8_t MSG_TYPE_RESPONSE = 0x01;

// AC Mode codes
enum ACMode : uint8_t {
  MODE_FAN_ONLY = 0,
  MODE_HEAT = 1,
  MODE_COOL = 2,
  MODE_DRY = 3,
  MODE_AUTO = 4
};

// Fan speed codes
enum FanSpeed : uint8_t {
  FAN_OFF = 0,
  FAN_AUTO = 1,
  FAN_QUIET = 2,
  FAN_LOW = 10,
  FAN_MEDIUM = 14,
  FAN_HIGH = 16,
  FAN_TURBO = 18
};

// Sleep mode codes
enum SleepMode : uint8_t {
  SLEEP_OFF = 0,
  SLEEP_1 = 1,
  SLEEP_2 = 2,
  SLEEP_3 = 4,
  SLEEP_4 = 8
};

// Device status structure (packed)
#pragma pack(push, 1)
struct DeviceStatus {
  uint8_t header[16];
  uint8_t wind_status;
  uint8_t sleep_status;
  uint8_t mode_and_power;  // Bits: [7:4] = mode, [3] = power, [2:0] = other
  uint8_t temperature_setting;
  uint8_t temperature_current;
  uint8_t pipe_temperature;
  uint8_t humidity_setting;
  uint8_t humidity_current;
  uint8_t reserved1[8];
  uint8_t swing_status;     // Bit 7 = up/down, Bit 6 = left/right
  uint8_t turbo_eco_status; // Bit 1 = turbo, Bit 2 = eco
  uint8_t reserved2;
  uint8_t quiet_status;     // Bit 2 = quiet mode
  uint8_t led_status;       // Bit 7 = LED on/off
  uint8_t reserved3[4];
  uint8_t compressor_frequency;
  uint8_t compressor_frequency_setting;
  uint8_t compressor_frequency_send;
  int8_t outdoor_temperature;
  int8_t outdoor_condenser_temperature;
  int8_t compressor_exhaust_temperature;
  int8_t target_exhaust_temperature;
  uint8_t extra_data[15];
  uint16_t checksum;
  uint8_t footer[2];
};
#pragma pack(pop)

class HisenseClimate : public climate::Climate, public uart::UARTDevice, public Component {
 public:
  HisenseClimate(uart::UARTComponent *parent) : uart::UARTDevice(parent) {}

  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::DATA; }

  // Climate interface
  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;
  
  // Name setter
  void set_name(const std::string &name) { this->name_ = name; }

  // Sensor setters for external access
  void set_compressor_frequency_sensor(sensor::Sensor *sensor) {
    compressor_frequency_sensor_ = sensor;
  }
  void set_outdoor_temperature_sensor(sensor::Sensor *sensor) {
    outdoor_temperature_sensor_ = sensor;
  }
  void set_pipe_temperature_sensor(sensor::Sensor *sensor) {
    pipe_temperature_sensor_ = sensor;
  }

 protected:
  // Command building and sending
  void send_command(const std::vector<uint8_t> &command);
  void send_power_command(bool on);
  void send_mode_command(ACMode mode);
  void send_temperature_command(uint8_t temp);
  void send_fan_command(FanSpeed speed);
  void send_swing_command(bool vertical, bool horizontal);
  void send_turbo_command(bool on);
  void send_eco_command(bool on);
  void send_quiet_command(bool on);
  void send_led_command(bool on);
  void send_sleep_command(SleepMode mode);
  void query_status();

  // Protocol handling
  bool parse_frame(const uint8_t *data, size_t len);
  uint16_t calculate_checksum(const uint8_t *data, size_t start, size_t end);
  void process_status(const DeviceStatus *status);
  
  // Helper methods
  climate::ClimateMode ac_mode_to_climate_mode(ACMode mode);
  ACMode climate_mode_to_ac_mode(climate::ClimateMode mode);
  climate::ClimateFanMode fan_speed_to_climate_fan(FanSpeed speed);
  FanSpeed climate_fan_to_fan_speed(climate::ClimateFanMode fan);
  void update_sensor(sensor::Sensor *sensor, float value);

 private:
  // Component name
  std::string name_;
  
  // State tracking
  bool power_state_{false};
  ACMode current_mode_{MODE_COOL};
  uint8_t target_temperature_{24};
  uint8_t current_temperature_{20};
  FanSpeed fan_speed_{FAN_AUTO};
  bool swing_vertical_{false};
  bool swing_horizontal_{false};
  bool turbo_mode_{false};
  bool eco_mode_{false};
  bool quiet_mode_{false};
  bool led_enabled_{true};
  SleepMode sleep_mode_{SLEEP_OFF};
  
  // Communication state
  std::vector<uint8_t> rx_buffer_;
  std::queue<std::vector<uint8_t>> tx_queue_;
  uint32_t last_query_time_{0};
  uint32_t last_command_time_{0};
  bool waiting_for_response_{false};
  uint8_t retry_count_{0};
  
  // Sensors
  sensor::Sensor *compressor_frequency_sensor_{nullptr};
  sensor::Sensor *outdoor_temperature_sensor_{nullptr};
  sensor::Sensor *pipe_temperature_sensor_{nullptr};
  
  // Constants
  static constexpr uint32_t QUERY_INTERVAL_MS = 2000;
  static constexpr uint32_t COMMAND_TIMEOUT_MS = 500;
  static constexpr uint8_t MAX_RETRIES = 3;
  static constexpr size_t MAX_BUFFER_SIZE = 256;
};

}  // namespace hisense_ac
}  // namespace esphome