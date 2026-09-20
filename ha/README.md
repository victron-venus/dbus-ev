# Mercedes via Cerbo MQTT

This Home Assistant custom integration receives data only from HA's already
configured MQTT broker. It makes no connection to Mercedes, stores no Mercedes
credentials and issues no vehicle commands.

The integration retains domain `mbapi2020`, upstream VIN-based unique IDs, sensor
names, units, translations and value mappings. Reconfigure the existing entry
after replacing the component to preserve entity IDs, history and automations.
Do not delete that entry or its device/entity registry records during migration.
The old cloud implementation and its credentials are removed, while its local
identity records are reused.

Configure the Cerbo portal ID, VIN and optional topic prefix. For this installation,
the existing Mosquitto bridge adds `victron/`; use that prefix. A direct connection
to the Cerbo broker would use an empty prefix.

On Cerbo, dbus-ev publishes QoS 1 retained snapshots and availability:

- `mercedes/<portal>/<VIN>/state` — schema 1, receipt time, revision, normalized
  vehicle attributes with original timestamps, and limited display metadata.
- `mercedes/<portal>/availability` — `online` / `offline`, including a last will.

The reserved `N/` tree is not writable by ordinary clients on the tested Venus
FlashMQ broker. Custom telemetry therefore uses `mercedes/`. Add this inbound-only
rule to the existing Cerbo bridge (do not start another bridge):

```conf
topic mercedes/# in 1 victron/
```

HA then subscribes to `victron/mercedes/<portal>/<VIN>/state` and
`victron/mercedes/<portal>/availability`. No command topics are added.

Sensors, binary sensors, GPS (when supplied) and read-only window covers are
provided. Former command buttons and writable climate switches are not loaded;
climate state remains in the existing preclimate status sensor. The value decoder
supports both legacy VEP and current VSU payloads. Retained snapshots do not renew
their source receipt time; stale data is unavailable after the configured timeout.

The MIT upstream license is included. See [provenance](../docs/mercedes-upstream.md)
and [migration](../docs/mercedes-migration.md). Remove this component from HACS's
upstream update management before replacement, so automatic updates cannot restore
the old cloud client.
