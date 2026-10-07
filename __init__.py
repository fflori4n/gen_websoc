from __future__ import annotations

import logging
import asyncio
from datetime import datetime

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_change

from .lib import internal_var
from .lib.config import CONFIG_SCHEMA
from .lib.constants import DOMAIN
from .lib.models import Field_device
from .lib.service import service_call_enqueue_and_respond
from .lib.state import clear_all_states, request_worker, update_entities_from_internal_state, reset_stale_sensors
from .lib.types_a_consts import ServiceType

_LOGGER = logging.getLogger(__name__)

async def async_setup(ha_instance: HomeAssistant, ha_config: ConfigType) -> bool:
    
    internal_var.ha = ha_instance
    internal_var.configuration = ha_config

    _LOGGER.debug("setting up integration")

    # load the predefined sensors from HA configuration.yaml
    for predefined_device in ha_config.get(DOMAIN, []):
        await asyncio.sleep(0)
        internal_var.field_dev_list.append(Field_device(ha_instance, predefined_device))

    # initialize all the predefined sensors with their default value
    await update_entities_from_internal_state(ha_instance)

    # In case Custom component goes offline, get a callback to clean up entities - in this case to set them to None so that gap will show up on history graph.
    ha_instance.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda event: clear_all_states(event, ha_instance))

    for device in internal_var.field_dev_list:
        if device.platform == "websoc":
            ha_instance.services.async_register(DOMAIN,f"{device.name}.{ServiceType.SET_VALUE.value}",service_call_enqueue_and_respond)
            ha_instance.services.async_register(DOMAIN,f"{device.name}.{ServiceType.SET_TIMESTAMPED_VALUE.value}",service_call_enqueue_and_respond)
        else:
            _LOGGER.error("config: device platform %s is not recognized, %s disabled.",device.platform,device.name)
            return True

    async def periodic_callback(now):
        #_LOGGER.debug("Minute mark!")
        await reset_stale_sensors(ha_instance, datetime.now())
        await update_entities_from_internal_state(ha_instance)

    remove_listener = async_track_time_change(ha_instance, periodic_callback, second=25 )
    ha_instance.data[DOMAIN] = remove_listener

    _LOGGER.warning("setup done.")
    return True