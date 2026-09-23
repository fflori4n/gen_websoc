from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from homeassistant.core import HomeAssistant

from .internal_var import field_dev_list, unprocessed_requests
from .models import Field_device, Field_sensor
from .service import process_request

_LOGGER = logging.getLogger(__name__)


def set_measurement(ha: HomeAssistant, field_device: Field_device, new_entity: Field_sensor):

    if (not new_entity.name) or (not field_device.name):
        raise ValueError("Field device or its entity has an invalid name")

    entity_id = f"{field_device.name}.{new_entity.name}"

    _LOGGER.debug("ha.states.async.set: %s = %s w attr: %s", entity_id, new_entity.state, new_entity.attributes)
    ha.add_job(ha.states.async_set, entity_id, str(new_entity.state), new_entity.attributes or {}, False)


async def update_entities_from_internal_state(ha: HomeAssistant):
    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            if not field_sensor.ha_state_up_to_date:
                set_measurement(ha, field_dev, field_sensor)
            field_sensor.ha_state_up_to_date = True


async def reset_stale_sensors(ha: HomeAssistant, current_time: datetime):
    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            field_sensor.clear_if_stale(current_time)


async def request_worker(hass: HomeAssistant):
    stale_check_interval = 20.0
    next_stale_check = time.monotonic() + stale_check_interval

    while True:
        await update_entities_from_internal_state(hass)

        now = time.monotonic()
        timeout = max(0.0, next_stale_check - now)

        try:
            request = await asyncio.wait_for(unprocessed_requests.get(),timeout=timeout)
        except asyncio.TimeoutError:
            await reset_stale_sensors(hass, datetime.now())
            next_stale_check = time.monotonic() + stale_check_interval
            continue

        try:
            await process_request(hass, request)
        except Exception:
            _LOGGER.exception("Failed processing request")
        finally:
            unprocessed_requests.task_done()

        if time.monotonic() >= next_stale_check:
            await reset_stale_sensors(hass, datetime.now())
            next_stale_check = time.monotonic() + stale_check_interval


async def clear_all_states(hass):
    _LOGGER.debug("HA service is shutting down.")

    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            field_sensor.clear_value()

    await update_entities_from_internal_state(hass)
    _LOGGER.debug("Ready to go offline.")
