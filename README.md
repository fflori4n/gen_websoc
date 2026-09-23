# gen_websoc
Homeassistant custom component for communicating with some sensors using the websoc endpoint

## Why choose websocket?

Areas where websoc shines:
   - Websocket is a good way to transmit large ammounts of data in a short time, it works well with a custom component that recieves bulk JSON and will later process and transfer the values to homeassistant.
   - It can get around CGNAT by using the regular web ports, other ports such as for MQTT ??1993?? might be blocked by the ISP. This works well with selfhosted homeassistant server.

Downsides:
   - Very non standard way of interfacing with HA, at least right now, fairly complicated and needs special token to be generated.
   - Needs custom component as backend ( as opposed to using REST api of HA, which works out of the box, but is more limited)
   - Not easy to change the route of the data, with MQTT it is easy to connect the broker to any other piece of software e.g. Grafana/ Influx DB, with websocket this custom component is the "Broker" the backend which is necesseary and sort of hardcoded.
   - downsides boil down to not being very user friendly.

## Optimized for fast bulk data transmission from field device to server using JSON
**Short ammount of time to transfer the measurements** is the priority here, because from the embedded sensor side:
   
   `little time spent transfering data and waiting for acknowledge from server` -> `more time spent in deep sleep` -> `better battery life`

Optimisations that were made to speed up process:
- Send multiple payloads in a single websoc session (handshake is done only once ??as opposed to the way it works with REST api??)
- Group values of different entities together into the same payload
- Send only the necesseary info, key and value, other data such a as HA attributes, icon, timeout, measurement class are predefined in `configuration.yaml`, `TODO:` add endpoint to set them if field_device needs to change it for some reason.
- `TODO:` Shorted field_sensor names so that the payload string gets shorter - probably negledgable gains...
- `TODO:` Group measurements with different timestamps
- Split validation of incoming packets into parts: 
    - fast check - will do a quick structure and JSON check and send acknowlidge as fast as possible.
    - Do the detailed processing later, store valuse inside custom component
    - Transfer Custom component values to HA occasionally