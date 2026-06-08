import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import (
    DEVICE_CLASS_TEMPERATURE,
    ENTITY_CATEGORY_DIAGNOSTIC,
    ICON_HEATING_COIL,
    ICON_THERMOMETER,
    STATE_CLASS_MEASUREMENT,
    UNIT_CELSIUS,
)
from ..climate import (
    CONF_HISENSE_ID,
    AirConditioner,
)


SensorTypeEnum = AirConditioner.enum("SubSensorType", True)

CONF_INDOOR_COIL_TEMPERATURE = "indoor_coil_temperature"
CONF_OUTDOOR_COIL_TEMPERATURE = "outdoor_coil_temperature"
CONF_INDOOR_TEMPERATURE = "indoor_temperature"
CONF_OUTDOOR_TEMPERATURE = "outdoor_temperature"


# NOTE: Indoor humidity is intentionally not exposed.
# On observed Hisense status frames, body[21] is a static 0x80 flag byte,
# not a humidity reading. The previous mapping produced "128 %" in HA.


SENSOR_TYPES = {
    CONF_INDOOR_COIL_TEMPERATURE: sensor.sensor_schema(
        unit_of_measurement=UNIT_CELSIUS,
        icon=ICON_HEATING_COIL,
        accuracy_decimals=0,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    CONF_OUTDOOR_COIL_TEMPERATURE: sensor.sensor_schema(
        unit_of_measurement=UNIT_CELSIUS,
        icon=ICON_HEATING_COIL,
        accuracy_decimals=0,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    CONF_INDOOR_TEMPERATURE: sensor.sensor_schema(
        unit_of_measurement=UNIT_CELSIUS,
        icon=ICON_THERMOMETER,
        accuracy_decimals=0,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
    CONF_OUTDOOR_TEMPERATURE: sensor.sensor_schema(
        unit_of_measurement=UNIT_CELSIUS,
        icon=ICON_THERMOMETER,
        accuracy_decimals=0,
        device_class=DEVICE_CLASS_TEMPERATURE,
        state_class=STATE_CLASS_MEASUREMENT,
        entity_category=ENTITY_CATEGORY_DIAGNOSTIC,
    ),
}

CONFIG_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_HISENSE_ID): cv.use_id(AirConditioner),
    }
).extend({cv.Optional(type): schema for type, schema in SENSOR_TYPES.items()})


async def to_code(config):
    paren = await cg.get_variable(config[CONF_HISENSE_ID])

    for type, _ in SENSOR_TYPES.items():
        if conf := config.get(type):
            sens = await sensor.new_sensor(conf)
            sensor_type = getattr(SensorTypeEnum, type.upper())
            cg.add(paren.set_sub_sensor(sensor_type, sens))
