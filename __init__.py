from __future__ import annotations
import asyncio
import datetime
from datetime import datetime, timedelta
import time
import pytz
import logging
import json
import math


import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from enum import Enum
from homeassistant.core import HomeAssistant
from homeassistant.components import persistent_notification
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import track_time_interval, async_call_later
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, EVENT_HOMEASSISTANT_STARTED
import queue
from typing import Any, TypedDict



#from .lib.Web_sensor import Custom_Websoc_Sensor_Tag, Custom_Websoc_Sensor
# The domain of your component. Should be equal to the name of your component.
DOMAIN = 'gen_websoc'

CONF_NAME = 'name'
CONF_PLATFORM = "platform"
CONF_TAG_TEMPLATE_LIST = 'tag_templates'
DEFAULT_NAME = '_unnamed_ws_sensor'
DEFAULT_PLATFORM = '_undef'

_LOGGER = logging.getLogger(__name__)
LOG_PREFIX = f"[{DOMAIN}]: "


CONF_TAG_TEMPLATE_LIST = "tag_templates"

DEFAULT_NAME = "weather_station"

def validate_tag_template(value):
    """Validate a single tag template."""
    schema = vol.Schema(
        {
            vol.Required("name"): cv.string,
            vol.Optional("state"): vol.Any(None, cv.string, int, float, bool),
            vol.Optional("friendly_name"): cv.string,
            vol.Optional("device_class"): cv.string,
            vol.Optional("unit_of_measurement"): cv.string,
            vol.Optional("state_class"): cv.string,
            vol.Optional("timeout"): cv.string,
        },
        extra=vol.ALLOW_EXTRA,
    )
    return schema(value)

single_sensor_schema = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_PLATFORM, default=DEFAULT_PLATFORM): cv.string,
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

ha : HomeAssistant
configuration : ConfigType
unprocessed_requests : asyncio.Queue[Queued_service_call] = asyncio.Queue(maxsize=100)
field_dev_list : Field_device = []


class SpecialAttributes(str, Enum):
    SET_APPEAR_OFFLINE =            "_OFLN",
    SET_TIME_OF_MEASUREMENTS =      "_TM",
    SET_SENSOR_UNRELIABLE =         "_UNREL",
    SET_SENSOR_WARNING =            "_WARN",
    SET_SENSOR_ERROR =              "_ERR",
    SET_SENSOR_HELP =               "_HELP",
    SET_ZONE =                      "_ZONE",
    #SET_ICON =                      "_ICON",
    #SET_ICON_COLOR =                "_ICON_COLOR",
    PLS_SEND_PUSH_NOTIFICATION =    "_NOTIF",

class ServiceType(str, Enum):
    SET_VALUE = "set_values"
    SET_TIMESTAMPED_VALUE = "tmspec_set_values"

class Queued_service_call: # or use something that extends TypedDict?
    req_type: ServiceType
    device: str
    payload: dict[str, Any]
    timestamp: datetime
    obj_hash : int

    def __init__(self, req_type: str, device: str, payload: dict[str, Any], timestamp: datetime ) -> None:
        self.req_type = req_type
        self.device = device
        self.payload = payload
        self.timestamp = timestamp

        # hash of this new call, without considering timestamp so that if same packet is recieved multiple times, it will be filtered out.
        self.obj_hash = hash(json.dumps((self.req_type, self.device, self.payload), sort_keys=True))

    def __repr__(self):
        return f"QREQ: {self.req_type} from {self.device} : {self.timestamp} : {json.dumps(self.payload, indent=2)}"

    def __str__(self):
        return f"QREQ: {self.req_type} from {self.device} : {self.timestamp} : {json.dumps(self.payload, indent=2)}"

    def __hash__(self):
        return self.obj_hash

class Field_sensor:

    name = ""
    state = None
    attributes = {}
    special_attributes = {}

    last_measurement_recieved_tm    : datetime | None = None
    measurement_goes_stale_tm       : datetime | None = None
    report_timout_after_sec         = None
    measurement_stale               = False

    _STALE_VALUE                    = None  # as a default value, I will use None, because it shows up as gaps in homeassistant UI history graphs             

    ha_state_up_to_date = False      # This is mosltly just a signal that state inside custom component sensor list was updated, and the value needs to be transfered to HA state as well, naming is not the best.

    def __init__(self, template_map):
        global ha_state_up_to_date

        self.name = template_map["name"]
        self.state = template_map["state"]
        self.report_timout_after_sec = int(template_map["timeout"]) * 60
        #self.attributes.update(template_map["friendly_name"])
        #self.attributes.update(template_map["state_class"])

        ha_state_up_to_date = False

    def update_loc_state(self, new_state, time_of_rx : datetime):
        global ha_state_up_to_date

        self.last_measurement_recieved_tm = time_of_rx
        self.measurement_goes_stale_tm = self.last_measurement_recieved_tm + timedelta(seconds=self.report_timout_after_sec)

        if self.state == new_state:
            pass
        else:
            self.state = new_state
            #ha_state_up_to_date = False
        ha_state_up_to_date = False # Note: think about this, this will create additional work, but the state change will be recoreded in HA? or at least it is up to HA to show this change?

    def clear_if_stale(self, current_time: datetime) -> bool:
        global ha_state_up_to_date

        if(not self.report_timout_after_sec) or (not self.measurement_goes_stale_tm) or (not current_time):
            return True

        self.measurement_stale = (current_time >= self.measurement_goes_stale_tm)

        if self.measurement_stale and (self.state != self._STALE_VALUE):
            self.state = self._STALE_VALUE
            ha_state_up_to_date = False
            _LOGGER.debug(f"{self.name} is in timeout, setting internal state to stale.")

        return self.measurement_stale 

    def clear_value(self):
        self.state = None

    def __repr__(self):
        return f"FIELD_SENSOR: {self.name}, {self.state}, with ATTR: {(item for item in self.attributes)}"
    
    def __str__(self):
        return f"FIELD_SENSOR: {self.name}, {self.state}, with ATTR: {(item for item in self.attributes)}"

class Field_device:
    
    ha_instance : HomeAssistant

    # all the info contained in config, defined by the user:
    name = '_UNDEF'
    platform = None
    field_sensors = []
    # description = None
    # zone, lattitude longitude accuracy etc.
    # is battery powered
    # expected update period

    def __init__(self, ha_instance: HomeAssistant, field_dev):

        self.ha_instance = ha_instance
        self.name = field_dev["name"]
        self.platform = field_dev["platform"]

        for sensor_template in field_dev["tag_templates"]:
            try:
                new_field_sensor = Field_sensor(sensor_template)
                self.field_sensors.append(new_field_sensor)
            except Exception as e:
                _LOGGER.debug(f"Error adding sensor from template: {e}")
                pass
        return

    def __repr__(self):
         return f"SENSOR_DEVICE: {self.name}, {self.platform}, Sensors: {self.field_sensors}"
    
    def __str__(self):
         return f"SENSOR_DEVICE: {self.name}, {self.platform}, Sensors: {self.field_sensors}"

# Operations that should be grouped with either field dev or field sensor
def get_field_sensor_from_list(field_device : Field_device, sensor_name : str) -> Field_sensor:
    selected_field_sensor = next((sensor for sensor in field_device.field_sensors if sensor.name == sensor_name), None)
        
    if selected_field_sensor is None:
        raise ValueError(f"Could not find sensor {sensor_name} under {field_device.name}\'s sensors")
    
    return selected_field_sensor

def get_field_device_from_list(field_device_name : str) -> Field_device:
    selected_field_dev = next((dev for dev in field_dev_list if dev.name == field_device_name), None)
        
    if selected_field_dev is None:
        raise ValueError(f"Could not find device {field_device_name} in device list")
    
    return selected_field_dev


def set_measurement(ha: HomeAssistant, field_device : Field_device, new_entity : Field_sensor):

    if not new_entity.name:
        raise ValueError("entity name is None or empty")

    entity_id = f"{field_device.name}.{new_entity.name}"

    _LOGGER.warning("HA.STATES.SET: %s = %s w attr: %s", entity_id, new_entity.state, new_entity.attributes)
    ha.add_job(ha.states.async_set, entity_id, str(new_entity.state), new_entity.attributes or {}, False )


def on_set_val(ha: HomeAssistant, request: Queued_service_call):

    field_device_name = request.device
    time_of_request = request.timestamp
    _LOGGER.debug(f"Processing on_set_val from: {request.device}")

    selected_field_dev : Field_device = None
    try:
        selected_field_dev = get_field_device_from_list(field_device_name)
    except Exception as e:
        raise HomeAssistantError(e)

    # Clean the dictionary of all the SPECIAL tags first

    # Iterate over attributes, find the corresponding field_sensor and update it's value and metadata.
    for key, value in request.payload.items():

        selected_field_sensor : Field_sensor = get_field_sensor_from_list(selected_field_dev, key)
        _LOGGER.debug(f"  Updating: {selected_field_sensor.name}, it's new value will be: {value}")
        selected_field_sensor.update_loc_state(value, time_of_request)


async def process_request( ha: HomeAssistant, request: Queued_service_call ) -> None:

    # @Note: 20ms is the maximum expected gap between the two calls, if it is longer, it is probably the end/ all calls transmitted from a single device. Others can wait until next processing loop
    await asyncio.sleep(0.2)  # It is probably a good time to yield here in case there is another service call.
    match request.req_type:
        case ServiceType.SET_VALUE:
            _LOGGER.debug(f"Calling processing for set_val")
            time.sleep(0.2)
            on_set_val(ha, request)
        case ServiceType.SET_TIMESTAMPED_VALUE:
            pass
        case _:
            _LOGGER.debug(f"Failed to route {request.type} to be processed.")

async def update_entities_from_internal_state(ha: HomeAssistant):

    for field_dev in field_dev_list:
        field_dev : Field_device

        for field_sensor in field_dev.field_sensors:
            field_sensor : Field_sensor
            #if field_sensor.ha_state_up_to_date == False:
            set_measurement(ha, field_dev, field_sensor)
            #    field_sensor.ha_state_up_to_date = True
                

async def reset_stale_sensors(ha: HomeAssistant, current_time: datetime):
    _LOGGER.debug(f"Checking for stale sensors")

    for field_dev in field_dev_list:
        field_dev : Field_device
    
        for field_sensor in field_dev.field_sensors:
            field_sensor : Field_sensor
            field_sensor.clear_if_stale(current_time)


async def request_worker(hass: HomeAssistant):
    stale_check_interval = 20.0
    next_stale_check = time.monotonic() + stale_check_interval

    while True:
        await update_entities_from_internal_state(hass)

        now = time.monotonic()
        timeout = max(0.0, next_stale_check - now)

        try:
            request: Queued_service_call = await asyncio.wait_for(
                unprocessed_requests.get(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            # No request arrived before the stale-check deadline.
            await reset_stale_sensors(hass, datetime.now())
            next_stale_check = time.monotonic() + stale_check_interval
            continue

        try:
            await process_request(hass, request)
        except Exception:
            _LOGGER.exception("Failed processing request")
        finally:
            unprocessed_requests.task_done()

        # Processing the request may have taken long enough to cross
        # the stale-check deadline.
        if time.monotonic() >= next_stale_check:
            await reset_stale_sensors(hass, datetime.now())
            next_stale_check = time.monotonic() + stale_check_interval


async def clear_all_states(hass):
    _LOGGER.debug(f"HA service is shutting down.")

    for field_dev in field_dev_list:
        field_dev : Field_device
    
        for field_sensor in field_dev.field_sensors:
            field_sensor : Field_sensor
            field_sensor.clear_value()

    await update_entities_from_internal_state(hass)  
    _LOGGER.debug(f"Ready to go offline.")

def validate_service_request(service_obj : ServiceCall, check_dev_exists : bool):
    field_device_name = service_obj.service[:service_obj.service.rfind(".")]

    try:
        selected_field_dev = get_field_device_from_list(field_device_name)
    except Exception as e:
        raise HomeAssistantError(e)
    
    try:
        service_data = dict(service_obj.data)
    except Exception as e:
        raise HomeAssistantError(f"service data is not parsable")

    return field_device_name, service_data

async def service_call_enqueue_and_respond(service_obj : ServiceCall) -> None:
    global unprocessed_requests

    #_LOGGER.debug(f"Callback: {service_obj.service} : {service_obj.data}")

    # Check which service call is it exactly, this is used to later route the ServiceCall when taken from queue
    try:
        service_type = ServiceType(service_obj.service.split(".", 1)[1])
    except ValueError:
        raise HomeAssistantError("Unknown service: %s", service_obj.service)

    # If this passes, request is good from a formatting perspective insert it into proc. queue
    # respond with positive response - But we will think about actually inserting the values into HA later...
    field_device_name,service_data = validate_service_request(service_obj, check_dev_exists = True)
   
    request = Queued_service_call(
        req_type = service_type,
        device = field_device_name,
        payload = service_data,
        timestamp = datetime.now()
        # Hash will be calculated in constructor
    )

    try:
        # first chcek if packet is already in queue
        # NOTE: using unprocessed_requests._queue could create some issues, because it is not thread safe, but the worst that can happen here is that it will process more requests than actually needed. 
        if next((service_call for service_call in unprocessed_requests._queue if service_call.obj_hash == request.obj_hash), None) is None:
            unprocessed_requests.put_nowait(request)
            _LOGGER.debug(f"New service call was added to queue: { request }, free slots available: {unprocessed_requests.maxsize - unprocessed_requests.qsize()}")
        #else:
        #_LOGGER.debug(f"Servicecall already in queue")
    except asyncio.QueueFull:
        raise HomeAssistantError("failed insert into unprocessed_requests queue")
    
    # Respond to client with positive response.
    return True

def setup(ha_instance: HomeAssistant, ha_config: ConfigType) -> bool:

    global ha, configuration

    ha = ha_instance
    configuration = ha_config

    _LOGGER.warning("setting up component.")

    predefined_devices = configuration.get(DOMAIN, [])
    #_LOGGER.debug(f"Sensors: {predefined_devices[0]}")
    for predefined_device in predefined_devices:
        #_LOGGER.debug("Sensors:")
        #_LOGGER.debug(Field_device(ha, predefined_device))
        field_dev_list.append(Field_device(ha, predefined_device))

    for device in field_dev_list:
        device : Field_device

        _LOGGER.debug(f"setting up {device}")

        if device.platform == "websoc":
            _LOGGER.debug(f"setup: registering endpoints for {device.name}")
            ha.services.register(DOMAIN, (device.name + "." + ServiceType.SET_VALUE.value), service_call_enqueue_and_respond)
            ha.services.register(DOMAIN, (device.name + "." + ServiceType.SET_TIMESTAMPED_VALUE.value), service_call_enqueue_and_respond)
            _LOGGER.debug(f"{DOMAIN}, {device.name}.set_values")
        else:
            _LOGGER.error(f"config: device platform {device.platform} is not recognized, {device.name} disabled.")
            return True

    #update_entities_from_fielddevs(ha)
    update_entities_from_internal_state(ha) # Not awaiting here!

    # Create separate worker for long processing, checking sensor timeouts and alerts
    ha.async_create_task(request_worker(ha))

    # listen for HA stop to disconnect
    ha.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, clear_all_states())
    

    return True