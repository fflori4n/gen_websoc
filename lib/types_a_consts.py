from enum import Enum

class SpecialAttributes(str, Enum):
    SET_APPEAR_OFFLINE =            "_OFLN",
    SET_TIME_OF_MEASUREMENTS =      "_TM",
    SET_SENSOR_UNRELIABLE =         "_UNREL",
    SET_SENSOR_WARNING =            "_WARN",
    SET_SENSOR_ERROR =              "_ERR",
    SET_SENSOR_HELP =               "_HELP",
    SET_ZONE =                      "_ZONE",
    PLS_SEND_PUSH_NOTIFICATION =    "_NOTIF",
    #SET_ICON =                      "_ICON",
    #SET_ICON_COLOR =                "_ICON_COLOR",

class ServiceType(str, Enum):
    SET_VALUE = "set_values"
    SET_TIMESTAMPED_VALUE = "tmspec_set_values"