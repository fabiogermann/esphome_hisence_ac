"""Hisense AC External Component for ESPHome."""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID

# Create the namespace
hisense_ac_ns = cg.esphome_ns.namespace('hisense_ac')

# Import the climate component
from . import climate

# Configuration schema - this allows the component to be used
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(cg.Component),
})

# Empty to_code since the actual implementation is in climate.py
async def to_code(config):
    pass