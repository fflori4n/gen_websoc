from __future__ import annotations

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .constants import (
    CONF_NAME,
    CONF_PLATFORM,
    CONF_TAG_TEMPLATE_LIST,
    DEFAULT_NAME,
    DEFAULT_PLATFORM,
    DOMAIN,
)


def validate_tag_template(value):
    """Validate a single tag template."""
    schema = vol.Schema(
        {
            vol.Required("name"): cv.string,
            vol.Optional("state"): vol.Any(None, cv.string, int, float, bool),
            vol.Optional("friendly_name"): vol.Any(None, cv.string),
            vol.Optional("icon"): vol.Any(None, cv.string),
            vol.Optional("device_class"): vol.Any(None, cv.string),
            vol.Optional("unit_of_measurement"): vol.Any(None, cv.string),
            vol.Optional("state_class"): vol.Any(None, cv.string),
            vol.Optional("timeout"): vol.Any(None, cv.string),
            vol.Optional("icon"): vol.Any(None, cv.string),
        },
        extra=vol.ALLOW_EXTRA,
    )
    return schema(value)

TEMPLATE_OBJECT_SCHEMA = vol.Schema({
    vol.Optional("name"): cv.string,
    vol.Optional("state", default=None): vol.Any(cv.string, None),
    vol.Optional("icon", default=None): vol.Any(cv.string, None),
    vol.Optional("unit_of_measurement", default=None): vol.Any(cv.string, None),
    vol.Optional("friendly_name", default=None): vol.Any(cv.string, None),
    vol.Optional("device_class", default=None): vol.Any(cv.string, None),
    vol.Optional("state_class", default=None): vol.Any(cv.string, None),
    vol.Optional("timeout", default="1"): cv.string,
})

single_sensor_schema = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PLATFORM, default=DEFAULT_PLATFORM): cv.string,
        vol.Optional("common_template", default=[]): vol.All(
            cv.ensure_list,
            [TEMPLATE_OBJECT_SCHEMA],
            vol.Length(min=0, max=100),
        ),
        vol.Optional(
            CONF_TAG_TEMPLATE_LIST,
            default=[],
        ): vol.All(
            [validate_tag_template],
            vol.Length(min=1, max=100),
        ),
    }
)


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: [single_sensor_schema],
    },
    extra=vol.ALLOW_EXTRA,
)
