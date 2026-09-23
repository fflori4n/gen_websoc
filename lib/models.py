from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any
import logging

from homeassistant.core import HomeAssistant

from ..lib.types_a_consts import ServiceType
from .internal_var import field_dev_list

_LOGGER = logging.getLogger(__name__)

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

        # hash of this new call, without considering timestamp so that if same packet is recieved multiple times, it will have the same hash.
        self.obj_hash = hash(json.dumps((self.req_type, self.device, self.payload), sort_keys=True))

    def __repr__(self):
        return f"QREQ: {self.req_type} from {self.device} : {self.timestamp} : {json.dumps(self.payload, indent=2)}"

    def __str__(self):
        return f"QREQ: {self.req_type} from {self.device} : {self.timestamp} : {json.dumps(self.payload, indent=2)}"

    def __hash__(self):
        return self.obj_hash

class Field_sensor:

    _STALE_VALUE                    = None  # as a default value, I will use None, because it shows up as gaps in homeassistant UI history graphs
    _ATTR_FRIENDLY_NAME             = "friendly_name"
    _ATTR_DEVICE_CLASS              = "device_class"
    _ATTR_STATE_CLASS               = "state_class"
    _ATTR_UNIT_OF_MEASUREMENT       = "unit_of_measurement"
    _ATTR_ICON                      = "icon"    

    # Make sure to initialize all members, python is wierd in this regard, these become class variables
    name                            = ""
    state                           = None
    attributes                      = {}
    special_attributes              = {}

    last_measurement_recieved_tm    : datetime | None = None
    measurement_goes_stale_tm       : datetime | None = None
    report_timout_after_sec         = None
    measurement_stale               = False
    ha_state_up_to_date             : bool = False      # This is mosltly just a signal that state inside custom component sensor list was updated, and the value needs to be transfered to HA state as well, naming is not the best.

    list_of_attribute_keys = list([_ATTR_FRIENDLY_NAME, _ATTR_DEVICE_CLASS, _ATTR_STATE_CLASS, _ATTR_UNIT_OF_MEASUREMENT, _ATTR_ICON])      

    def __init__(self, template_map):

        self.name = template_map.get("name")
        self.state = template_map.get("state")
        self.report_timout_after_sec = int(template_map.get("timeout")) * 60
        self.attributes = {}

        for attr_key in self.list_of_attribute_keys:
            val = template_map.get(attr_key)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            self.attributes[attr_key] = val

        _LOGGER.debug(f"created local sensor {self.name} = {self.state} based on config template with attributes:{str(self.attributes)}")
        self.ha_state_up_to_date = False

    # @staticmethod
    # def is_truthy(val) -> bool:
    #     return val is not None and (not isinstance(val, str) or bool(val.strip()))

    def update_loc_state(self, new_state, time_of_rx : datetime):

        self.last_measurement_recieved_tm = time_of_rx
        self.measurement_goes_stale_tm = self.last_measurement_recieved_tm + timedelta(seconds=self.report_timout_after_sec)

        if self.state == new_state:
            pass
        else:
            self.state = new_state
            #self.ha_state_up_to_date = False
        self.ha_state_up_to_date = False # Note: think about this, this will create additional work, but the state change will be recoreded in HA? or at least it is up to HA to show this change?

    def clear_if_stale(self, current_time: datetime) -> bool:

        if(not self.report_timout_after_sec) or (not self.measurement_goes_stale_tm) or (not current_time):
            return True

        self.measurement_stale = (current_time >= self.measurement_goes_stale_tm)

        if self.measurement_stale and (self.state != self._STALE_VALUE):
            self.state = self._STALE_VALUE
            self.ha_state_up_to_date = False
            _LOGGER.debug(f"{self.name} is in timeout, setting internal state to stale.")

        return self.measurement_stale 

    def clear_value(self):
        self.state = None
        self.ha_state_up_to_date = False

    def __repr__(self):
        return f"FIELD_SENSOR: {self.name}, {self.state}, with ATTR: {(item for item in self.attributes)}"
    
    def __str__(self):
        return f"FIELD_SENSOR: {self.name}, {self.state}, with ATTR: {(item for item in self.attributes)}"

    @staticmethod
    def get_field_sensor_from_list(field_device : Field_device, sensor_name : str) -> Field_sensor:
        selected_field_sensor = next((sensor for sensor in field_device.field_sensors if sensor.name == sensor_name), None)
            
        if selected_field_sensor is None:
            raise ValueError(f"Could not find sensor {sensor_name} under {field_device.name}\'s sensors")
        
        return selected_field_sensor

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

    location_en = False
    # @TODO: implement zones and location tracking
    DEVICE_ZONE_LATITUDE = ""
    DEVICE_ZONE_LONGITUDE = ""
# source_type: gps
# latitude: 45.2496716
# longitude: 19.8370915
# gps_accuracy: 100
# altitude: 133
# course: 0
# speed: 0
# vertical_accuracy: 100

    def __init__(self, ha_instance: HomeAssistant, field_dev):

        self.ha_instance = ha_instance
        self.name = field_dev["name"]
        self.platform = field_dev["platform"]

        for sensor_template in field_dev["tag_templates"]:
            try:
                _LOGGER.debug(f"Creating new field sensor")
                new_field_sensor = Field_sensor(sensor_template)
                _LOGGER.debug(f"Appending to list of sensors")
                self.field_sensors.append(new_field_sensor)
            except Exception as e:
                _LOGGER.debug(f"Error adding sensor from template: {e}")
                continue
        return

    def __repr__(self):
         return f"SENSOR_DEVICE: {self.name}, {self.platform}, Sensors: {self.field_sensors}"
    
    def __str__(self):
         return f"SENSOR_DEVICE: {self.name}, {self.platform}, Sensors: {self.field_sensors}"

    @staticmethod
    def get_field_device_from_list(field_device_name : str) -> Field_device:
        selected_field_dev = next((dev for dev in field_dev_list if dev.name == field_device_name), None)
        
        if selected_field_dev is None:
            raise ValueError(f"Could not find device {field_device_name} in device list")
    
        return selected_field_dev