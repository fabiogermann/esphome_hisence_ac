"""Hisense AC Climate Component for ESPHome."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import climate, uart, sensor
from esphome import pins
from esphome.const import (
    CONF_ID,
    CONF_UART_ID,
    CONF_NAME,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_FREQUENCY,
    STATE_CLASS_MEASUREMENT,
    UNIT_CELSIUS,
    UNIT_HERTZ,
    ICON_THERMOMETER,
)
from esphome.core import CORE

from . import hisense_ac_ns

DEPENDENCIES = ["uart"]
AUTO_LOAD = ["sensor"]

# Define the HisenseClimate class
HisenseClimate = hisense_ac_ns.class_(
    "HisenseClimate", climate.Climate, uart.UARTDevice, cg.Component
)

# Configuration keys
CONF_COMPRESSOR_FREQUENCY_SENSOR = "compressor_frequency_sensor"
CONF_OUTDOOR_TEMPERATURE_SENSOR = "outdoor_temperature_sensor"
CONF_PIPE_TEMPERATURE_SENSOR = "pipe_temperature_sensor"
CONF_FLOW_CONTROL_PIN = "flow_control_pin"
CONF_DISPLAY_ENABLED = "display_enabled"

# Configuration schema - simplified without switches for now
CONFIG_SCHEMA = climate.CLIMATE_SCHEMA.extend(
    {
        cv.GenerateID(): cv.declare_id(HisenseClimate),
        cv.Required(CONF_UART_ID): cv.use_id(uart.UARTComponent),
        cv.Optional(CONF_COMPRESSOR_FREQUENCY_SENSOR): sensor.sensor_schema(
            unit_of_measurement=UNIT_HERTZ,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_FREQUENCY,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        cv.Optional(CONF_OUTDOOR_TEMPERATURE_SENSOR): sensor.sensor_schema(
            unit_of_measurement=UNIT_CELSIUS,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_TEMPERATURE,
            state_class=STATE_CLASS_MEASUREMENT,
            icon=ICON_THERMOMETER,
        ),
        cv.Optional(CONF_PIPE_TEMPERATURE_SENSOR): sensor.sensor_schema(
            unit_of_measurement=UNIT_CELSIUS,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_TEMPERATURE,
            state_class=STATE_CLASS_MEASUREMENT,
            icon=ICON_THERMOMETER,
        ),
        cv.Optional(CONF_FLOW_CONTROL_PIN): pins.gpio_output_pin_schema,
        cv.Optional(CONF_DISPLAY_ENABLED, default=True): cv.boolean,
    }
).extend(cv.COMPONENT_SCHEMA).extend(uart.UART_DEVICE_SCHEMA)


async def to_code(config):
    """Generate code for Hisense AC Climate component."""
    # Get UART reference
    uart_component = await cg.get_variable(config[CONF_UART_ID])
    
    # Create the climate component with UART
    var = cg.new_Pvariable(config[CONF_ID], uart_component)
    
    # Register the component first
    await cg.register_component(var, config)
    
    # Then register as climate
    await climate.register_climate(var, config)
    
    # Set name if provided
    if CONF_NAME in config:
        cg.add(var.set_name(config[CONF_NAME]))
    
    # Configure flow control pin for RS485
    if CONF_FLOW_CONTROL_PIN in config:
        pin = await cg.gpio_pin_expression(config[CONF_FLOW_CONTROL_PIN])
        cg.add(var.set_flow_control_pin(pin))
    
    # Configure display control
    if CONF_DISPLAY_ENABLED in config:
        cg.add(var.set_display_enabled(config[CONF_DISPLAY_ENABLED]))
    
    # Configure optional sensors
    if CONF_COMPRESSOR_FREQUENCY_SENSOR in config:
        sens_conf = config[CONF_COMPRESSOR_FREQUENCY_SENSOR]
        sens = await sensor.new_sensor(sens_conf)
        cg.add(var.set_compressor_frequency_sensor(sens))
    
    if CONF_OUTDOOR_TEMPERATURE_SENSOR in config:
        sens_conf = config[CONF_OUTDOOR_TEMPERATURE_SENSOR]
        sens = await sensor.new_sensor(sens_conf)
        cg.add(var.set_outdoor_temperature_sensor(sens))
    
    if CONF_PIPE_TEMPERATURE_SENSOR in config:
        sens_conf = config[CONF_PIPE_TEMPERATURE_SENSOR]
        sens = await sensor.new_sensor(sens_conf)
        cg.add(var.set_pipe_temperature_sensor(sens))