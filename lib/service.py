from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .internal_var import unprocessed_requests
from .models import Field_device, Field_sensor, Queued_service_call
from .types_a_consts import ServiceType

_LOGGER = logging.getLogger(__name__)


def on_set_val(ha: HomeAssistant, request: Queued_service_call):

    field_device_name = request.device
    time_of_request = request.timestamp
    _LOGGER.debug("Processing on_set_val from: %s", request.device)

    try:
        selected_field_dev = Field_device.get_field_device_from_list(field_device_name)
    except Exception as e:
        raise HomeAssistantError(e)

    for key, value in request.payload.items():
        selected_field_sensor = Field_sensor.get_field_sensor_from_list(selected_field_dev, key)
        _LOGGER.debug("Updating: %s, its new value will be: %s", selected_field_sensor.name, value)
        selected_field_sensor.update_loc_state(value, time_of_request)


async def process_request(ha: HomeAssistant, request: Queued_service_call) -> None:
    await asyncio.sleep(0.2)

    match request.req_type:
        case ServiceType.SET_VALUE:
            time.sleep(0.2)
            on_set_val(ha, request)
        case ServiceType.SET_TIMESTAMPED_VALUE:
            pass
        case _:
            _LOGGER.error("Failed to route %s to be processed.", request.req_type)


def validate_service_request(service_obj: ServiceCall, check_dev_exists: bool):
    field_device_name = service_obj.service[: service_obj.service.rfind(".")]

    try:
        Field_device.get_field_device_from_list(field_device_name)
    except Exception as e:
        raise HomeAssistantError(e)

    try:
        service_data = dict(service_obj.data)
    except Exception:
        raise HomeAssistantError("service data is not parsable")

    return field_device_name, service_data


async def service_call_enqueue_and_respond(service_obj: ServiceCall) -> None:
    try:
        service_type = ServiceType(service_obj.service.split(".", 1)[1])
    except ValueError:
        raise HomeAssistantError(f"Unknown service: {service_obj.service}")

    field_device_name, service_data = validate_service_request(service_obj, check_dev_exists=True)

    request = Queued_service_call(
        req_type=service_type,
        device=field_device_name,
        payload=service_data,
        timestamp=datetime.datetime.now(),
    )

    try:
        if next((service_call for service_call in unprocessed_requests._queue if service_call.obj_hash == request.obj_hash), None) is None:
            unprocessed_requests.put_nowait(request)
            _LOGGER.debug(
                "New service call was added to queue: %s, free slots available: %s",
                request,
                unprocessed_requests.maxsize - unprocessed_requests.qsize(),
            )
    except asyncio.QueueFull:
        raise HomeAssistantError("failed insert into unprocessed_requests queue")

    return True
