from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from homeassistant.core import HomeAssistant

from .internal_var import ha, field_dev_list, unprocessed_requests, _active_queue_worker
from .models import Field_device, Field_sensor
from .types_a_consts import ServiceType

_LOGGER = logging.getLogger(__name__)

def set_measurement(ha_instance: HomeAssistant, field_device: Field_device, new_entity: Field_sensor):

    if new_entity.ha_state_up_to_date:
        return True
    
    if (not new_entity.name) or (not field_device.name):
        raise ValueError("Field device or its entity has an invalid name")

    if not ha_instance:
        raise ValueError("Function called without valid homeassistant instance")

    ha_instance.add_job(ha_instance.states.async_set, f"{field_device.name}.{new_entity.name}", str(new_entity.state), new_entity.attributes or {}, False)
    _LOGGER.debug("HA_STATE_SET: %s.%s = %s", field_device.name, new_entity.name, new_entity.state)
    return True

async def update_entities_from_internal_state(ha_instance: HomeAssistant):
    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            field_sensor.ha_state_up_to_date = set_measurement(ha_instance, field_dev, field_sensor)
            await asyncio.sleep(0)

async def reset_stale_sensors(ha: HomeAssistant, current_time: datetime):
    global _active_queue_worker

    if _active_queue_worker is not None:
        try:
            await asyncio.wait_for(
                asyncio.shield(_active_queue_worker),
                timeout=30,
            )
        except asyncio.TimeoutError:
            _LOGGER.warning("Reset stale timed out waiting for queue worker to finish.")
            return

    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            await asyncio.sleep(0)
            field_sensor.clear_if_stale(current_time)

def on_set_val(ha: HomeAssistant, request: Queued_service_call):

    #_LOGGER.debug("Processing on_set_val from: %s", request.device)
    try:
        selected_field_dev = Field_device.get_field_device_from_list(request.device)
    except Exception as e:
        raise HomeAssistantError(e)

    for key, value in request.payload.items():
        selected_field_sensor = Field_sensor.get_field_sensor_from_list(selected_field_dev, key)
        selected_field_sensor.update_loc_state(value, request.timestamp)
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

    _LOGGER.warning("Request worker running.")

    while True:
        
        try:
            await asyncio.sleep(0)
            request = await asyncio.wait_for(unprocessed_requests.get(),timeout=5.0)
            #_LOGGER.debug(f"Request {request.req_type} from {request.device} is ready to be processed.")
        except asyncio.TimeoutError:
            _LOGGER.debug("No more requests, worker exiting")
            break

        try:
            await asyncio.sleep(0)
            try:
                await asyncio.wait_for(route_a_process_request(hass, request),timeout=15.0)
            except ValueError:
                pass
            
        except asyncio.TimeoutError:
            _LOGGER.error("Processing request timed out")
        except Exception:
            _LOGGER.exception("Failed processing request")

        finally:
            unprocessed_requests.task_done()

    await update_entities_from_internal_state(hass)

    _LOGGER.warning("Request worker done.")
    _active_queue_worker = None
    return
        
async def clear_all_states(event, ha_instance : HomeAssistant):

    _LOGGER.debug("component is preparing for HA shutdown")

    for field_dev in field_dev_list:
        for field_sensor in field_dev.field_sensors:
            field_sensor.clear_value()

    await update_entities_from_internal_state(ha_instance)
    _LOGGER.debug("finished.ready to go offline.")
