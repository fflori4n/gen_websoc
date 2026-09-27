from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from homeassistant.core import HomeAssistant

from .internal_var import field_dev_list, unprocessed_requests, _active_queue_worker
from .models import Field_device, Field_sensor
from .types_a_consts import ServiceType

_LOGGER = logging.getLogger(__name__)

def set_measurement(ha: HomeAssistant, field_device: Field_device, new_entity: Field_sensor):

    if (not new_entity.name) or (not field_device.name):
        raise ValueError("Field device or its entity has an invalid name")

    entity_id = f"{field_device.name}.{new_entity.name}"

    _LOGGER.debug("%s SET AS: %s", entity_id, new_entity.state)
    #_LOGGER.debug("%s SET AS: %s w attr: %s", entity_id, new_entity.state, new_entity.attributes)
    ha.add_job(ha.states.async_set, entity_id, str(new_entity.state), new_entity.attributes or {}, False)


async def update_entities_from_internal_state(ha: HomeAssistant):
    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            await asyncio.sleep(0)
            if not field_sensor.ha_state_up_to_date:
                #_LOGGER.debug("internal state transfer %s::%s", field_dev.name, field_sensor.name)
                set_measurement(ha, field_dev, field_sensor)
                pass
            field_sensor.ha_state_up_to_date = True


async def reset_stale_sensors(ha: HomeAssistant, current_time: datetime):
    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            field_sensor.clear_if_stale(current_time)

def on_set_val(ha: HomeAssistant, request: Queued_service_call):

    field_device_name = request.device
    time_of_request = request.timestamp
    #_LOGGER.debug("Processing on_set_val from: %s", request.device)

    try:
        selected_field_dev = Field_device.get_field_device_from_list(field_device_name)
    except Exception as e:
        raise HomeAssistantError(e)

    #_LOGGER.debug("Selected field device: %s", selected_field_dev.name)

    for key, value in request.payload.items():
        selected_field_sensor = Field_sensor.get_field_sensor_from_list(selected_field_dev, key)
        selected_field_sensor.update_loc_state(value, time_of_request)
        #_LOGGER.debug("Updated local state of  %s::%s = %s", selected_field_dev.name, selected_field_sensor.name, value)


async def route_a_process_request(ha: HomeAssistant, request: Queued_service_call) -> None:

    match request.req_type:
        case ServiceType.SET_VALUE:
            on_set_val(ha, request)
        case ServiceType.SET_TIMESTAMPED_VALUE:
            pass
        case _:
            _LOGGER.error("Failed to route %s to be processed.", request.req_type)

async def request_worker(hass: HomeAssistant):
    global _active_queue_worker

    _LOGGER.warning("Entered request worker.")

    while True:
        
        try:
            await asyncio.sleep(0)
            request = await asyncio.wait_for(unprocessed_requests.get(),timeout=5.0)
            _LOGGER.debug(f"Request {request.req_type} from {request.device} is ready to be processed.")
        except asyncio.TimeoutError:
            _LOGGER.debug("No more requests, worker exiting")
            break

        try:
            await asyncio.sleep(0)
            try:
                await asyncio.wait_for(route_a_process_request(hass, request),timeout=15.0)
                #await update_entities_from_internal_state(hass)
            except ValueError:
                pass
            
        except asyncio.TimeoutError:
            _LOGGER.error("Processing request timed out")
        except Exception:
            _LOGGER.exception("Failed processing request")

        finally:
            unprocessed_requests.task_done()

    await update_entities_from_internal_state(hass)

    _LOGGER.warning("Exited request worker")
    _active_queue_worker = None
    return
        
    # Run this once to clear all devices, and update mostly the attributes if config was changed while the Custom component was offline, or went offline without clearing states
    #await update_entities_from_internal_state(hass)

    
        # while not unprocessed_requests.empty():
        #     request = await unprocessed_requests.get()

        #     try:
        #         await process_request(hass, request)
        #     except Exception:
        #         _LOGGER.exception("Failed processing request")
        #     finally:
        #         unprocessed_requests.task_done()
    # stale_check_interval = 20.0
    # next_stale_check = time.monotonic() + stale_check_interval

    # while True:
    #     #_LOGGER.warning("Entered main task loop")
    #     #await update_entities_from_internal_state(hass)

    #     # now = time.monotonic()
    #     # timeout = max(0.0, next_stale_check - now)
    #     await asyncio.sleep(1)

        # try:
        #     request = await asyncio.wait_for(unprocessed_requests.get(),timeout=timeout)
        # except asyncio.TimeoutError:
        #     #await reset_stale_sensors(hass, datetime.now())
        #     next_stale_check = time.monotonic() + stale_check_interval
        #     continue

        # try:
        #     #await process_request(hass, request)
        #     pass
        # except Exception:
        #     _LOGGER.exception("Failed processing request")
        # finally:
        #     unprocessed_requests.task_done()

        # if time.monotonic() >= next_stale_check:
        #     #await reset_stale_sensors(hass, datetime.now())
        #     next_stale_check = time.monotonic() + stale_check_interval


async def clear_all_states(hass):
    _LOGGER.debug("HA service is shutting down.")

    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            field_sensor.clear_value()

    await update_entities_from_internal_state(hass)
    _LOGGER.debug("Ready to go offline.")
