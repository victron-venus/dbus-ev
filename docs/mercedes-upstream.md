# Mercedes protocol source

Adapted from [ReneNulschDE/mbapi2020](https://github.com/ReneNulschDE/mbapi2020/tree/aa6e9453a5da1cff79c8f427ccfcf079a06f247f), revision `aa6e9453a5da1cff79c8f427ccfcf079a06f247f`, version 0.41.0, MIT license.

`dbus_ev/mercedes/vendor` contains protocol schemas, region headers, value mappings and telemetry decoder; it has no Home Assistant dependency. The accompanying Home Assistant MQTT adapter retains upstream sensor names, unique IDs, units and enum mappings. Cloud authentication and command platforms are not loaded by the HA adapter. See the included LICENSE files.

The unified client also uses upstream's read-only widget REST fallback. After
120 seconds without initial data, or 600 seconds without vehicle updates, it reads
`/v1/vehicle/{vin}/vehicleattributes` using the same OAuth owner and HTTP session.
An otherwise healthy WebSocket stays open: its ping/pong heartbeat detects a dead
transport independently of telemetry age. Healthy vehicle push updates suppress
REST entirely. This is at most six widget polls per hour during quiet operation,
versus upstream's 180-second blocked-account poll cycle. Local D-Bus/HA/dashboard
cache reads never make cloud requests.

HTTP 429 from config, token refresh, REST or WebSocket pauses **all new HTTP
requests, reconnects and logins** for at least 30 minutes. Consecutive limits
increase this to 60, 120, 240 and 360 minutes; a longer `Retry-After` always wins.
Ordinary transport reconnects start at 60 seconds and double up to one hour.
Only a connection sustained for five minutes resets the backoff; a successful
handshake followed by another immediate disconnect does not. Authorization
rejections pause requests for six hours. The account owner's private
`<token-file>.limits.json` persists pauses and login limits across restarts and
package upgrades. Do not delete it to bypass a server limit.

Optional HTTP 429 login recovery uses the
same OAuth owner after the global cooldown; see
[recovery configuration](mercedes-migration.md#blocked-session-recovery).

The widget can return either legacy VEP or current VSU protobuf data. It may
provide only SoC, range and location. Missing fields are unknown in the REST
snapshot while the socket is unavailable; old push charging or door readings
are not marked fresh. A healthy socket that has delivered its initial full
snapshot still owns unchanged fields, and REST supplements that live stream.
The existing
MQTT `data mode` diagnostic distinguishes `pull` from `push`, and acquisition
timestamps expire normally if both transports fail. WebSocket recovery restores
the full push snapshot automatically.

A brief transport reconnect preserves the last acquired snapshot until its
configured freshness deadline (900 seconds by default). Reconnecting or polling
the cache never renews that deadline. A subsequent REST-only response replaces
the snapshot, so fields omitted by the widget become unknown immediately; a
client shutdown also marks its snapshot unavailable.
The push merge buffer belongs to the application session and survives socket
reconnects, as in upstream. Mercedes may resume with deltas instead of replaying
the full vehicle; an explicit full update still replaces the buffer.

When upgrading an existing installation, set both `MERCEDES_STALE_TIMEOUT` and
the HA MQTT entry's `stale_timeout` to 900 seconds for the ten-minute fallback.
Explicit shorter deadlines are preserved and may show unavailable between polls.
During rate limiting, availability expires normally; the client does not turn
old readings into fresh telemetry to hide the enforced pause.
