from __future__ import annotations

import logging

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .lib import internal_var
from .lib.config import CONFIG_SCHEMA
from .lib.constants import DOMAIN
from .lib.models import Field_device
from .lib.service import service_call_enqueue_and_respond
from .lib.state import clear_all_states, request_worker, update_entities_from_internal_state
from .lib.types_a_consts import ServiceType

_LOGGER = logging.getLogger(__name__)


def setup(ha_instance: HomeAssistant, ha_config: ConfigType) -> bool:
    internal_var.ha = ha_instance
    internal_var.configuration = ha_config

    _LOGGER.warning("setting up component.")

    predefined_devices = ha_config.get(DOMAIN, [])

    for predefined_device in predefined_devices:
        internal_var.field_dev_list.append(Field_device(ha_instance, predefined_device))

    # In case Custom component goes offline, get a callback to clean up entities - in this case to set them to None so that gap will show up on history graph.
    # NOTE: What if in case shutdown is immediate before cfg is read, then again the server is going offline anyways...
    ha_instance.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, clear_all_states(ha_instance))

    for device in internal_var.field_dev_list:
        _LOGGER.debug("setting up %s", device)

        if device.platform == "websoc":
            ha_instance.services.register(DOMAIN,f"{device.name}.{ServiceType.SET_VALUE.value}",service_call_enqueue_and_respond)
            ha_instance.services.register(DOMAIN,f"{device.name}.{ServiceType.SET_TIMESTAMPED_VALUE.value}",service_call_enqueue_and_respond)
        else:
            _LOGGER.error("config: device platform %s is not recognized, %s disabled.",device.platform,device.name)
            return True

    # Run this once to clear all devices, and update mostly the attributes if config was changed while the Custom component was offline, or went offline without clearing states
    update_entities_from_internal_state(ha_instance)

    # From now on, all tasks will be handled by request worker
    ha_instance.async_create_task(request_worker(ha_instance))

    return True