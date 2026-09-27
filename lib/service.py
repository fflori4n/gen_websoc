from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .internal_var import unprocessed_requests, _active_queue_worker
from .models import Field_device, Field_sensor, Queued_service_call
from .types_a_consts import ServiceType
from .state import request_worker

_LOGGER = logging.getLogger(__name__)

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

            # Start up the worker task that will drain the requests
            ha_instance = service_obj.hass
            global _active_queue_worker
            if _active_queue_worker is None or _active_queue_worker.done():
                _active_queue_worker = ha_instance.async_create_task(request_worker(ha_instance))

    except asyncio.QueueFull:
        raise HomeAssistantError("failed insert into unprocessed_requests queue")

    return True
