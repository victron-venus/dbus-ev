# Mercedes protocol source

Adapted from [ReneNulschDE/mbapi2020](https://github.com/ReneNulschDE/mbapi2020/tree/aa6e9453a5da1cff79c8f427ccfcf079a06f247f), revision `aa6e9453a5da1cff79c8f427ccfcf079a06f247f`, version 0.41.0, MIT license.

`dbus_ev/mercedes/vendor` contains protocol schemas, region headers, value mappings and telemetry decoder; it has no Home Assistant dependency. The accompanying Home Assistant MQTT adapter retains upstream sensor names, unique IDs, units and enum mappings. Cloud authentication and command platforms are not loaded by the HA adapter. See the included LICENSE files.

The unified client also uses upstream's read-only widget REST fallback. After
25 seconds without initial data, or 180 seconds without vehicle updates, it reads
`/v1/vehicle/{vin}/vehicleattributes` using the same OAuth owner and HTTP session.
An otherwise healthy WebSocket stays open: its ping/pong heartbeat detects a dead
transport independently of telemetry age. During a WebSocket rate limit, REST
polling continues every three minutes; failed REST requests back off separately.
Both transports honor `Retry-After`, and no automatic password login is attempted.

The widget can return either legacy VEP or current VSU protobuf data. It may
provide only SoC, range and location. Missing fields are unknown in the REST
snapshot; old push charging or door readings are not marked fresh. The existing
MQTT `data mode` diagnostic distinguishes `pull` from `push`, and acquisition
timestamps expire normally if both transports fail. WebSocket recovery restores
the full push snapshot automatically.
