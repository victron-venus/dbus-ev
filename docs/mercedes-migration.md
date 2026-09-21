# Mercedes migration and rollback

## Prepared configuration

One dbus-ev process owns vehicle instance 22 (`ev.ha`) and charger instance 40
(`evcharger.charger`). One Mercedes connection feeds both and, when enabled, HA
MQTT. The device-local configuration enables publication; the tracked example
disables it. The original HA vehicle reader remains selectable.

Keep a private backup of both GX local configs, original service links/boot hooks,
the HA custom component and the affected config-entry/entity/device registry
records. Authorization exports contain secrets and must remain outside Git with
mode 0600. Never put them into release archives or MQTT payloads.

## Ordered cutover

1. Run the dbus-ev tests and the isolated HA runtime check. Provision optional GX
   dependencies using `install-mercedes-deps.sh`; it does not start a cloud client.
   Stage the code and check Python imports on the device before changing services.
2. Add `topic mercedes/# in 1 victron/` to the **existing** Mosquitto Cerbo bridge.
   Apply the ConfigMap and restart the single broker under the normal deployment
   process. A probe on `mercedes/<portal>/_route_check` must arrive at HA as
   `victron/mercedes/<portal>/_route_check` before proceeding.
3. Disable/unload the old mbapi2020 HA entry and verify its cloud socket is closed.
   Preserve its entry ID and entity registry records. Remove the upstream HACS
   repository from automatic update management before replacing the component.
4. Transfer the now-idle entry's **fresh** `region`, `device_guid` and `token`
   fields into `/data/setupOptions/dbus-ev/mercedes-token.json` with mode 0600.
   Do not reuse this token concurrently in HA. Password recovery is a separate
   opt-in described below. Alternatively
   use the standalone authorization CLI after stopping the old integration.
5. Uninstall/disable the standalone dbus-evcharger package through its setup
   script, including its boot hook. Its `/service/dbus-evcharger` link must be
   absent, and PackageManager must no longer automatically reinstall it. Preserve
   the old code/config for rollback. The dbus-ev installer refuses a second charger
   service owner before stopping its own worker.
6. Install dbus-ev with the prepared private configuration. For SetupHelper:
   `./setup install --ha-mqtt=on`. For workstation deployment use `./deploy.sh Cerbo`.
   Check worker heartbeat, `/Connected`, source freshness, both D-Bus identities,
   and the retained snapshot arriving through the MQTT bridge.
7. Replace `/config/custom_components/mbapi2020` with the included MQTT-only
   component (a clean replacement, not an overlay leaving old cloud modules).
   Restart HA to unload the previous Python module versions. Reconfigure the
   existing entry with portal ID, VIN and `topic_prefix = victron/`, then enable it.
   Reconfiguration **replaces** entry data, deleting Mercedes credentials.
   When using the HA REST flow API, pass `entry_id` at the top level beside
   `handler`; a nested `context` is ignored and starts a new-entry flow. Confirm
   the returned `step_id` is `reconfigure` before submitting MQTT settings.
8. Compare every previous sensor and binary-sensor entity ID and value type;
   check window states, invalid values, MQTT disconnect and stale retained data.
   Old command-only buttons and climate control switches are no longer provided.
   Confirm no HA process connects to Mercedes and only dbus-ev owns the GX charger.

Do not infer successful migration from a heartbeat alone. It proves the loop is
running, not receipt from Mercedes, MQTT delivery or current vehicle data.

## Rollback

Stop dbus-ev before restoring another Mercedes client. Save its most recently
rotated token back into the private rollback material: a pre-migration refresh
token may no longer be valid. Restore the old GX packages/configurations and their
single service owners. Restore the original HA component and re-enable its entry
with current credentials (reauthorize if needed). Restore the MQTT bridge
configuration if necessary. Keep entity registry identities intact throughout.

## Validation boundaries

Local tests cover protobuf ACKs, VEP/VSU conversion, partial updates, token
rotation/ownership, shared projections, freshness, MQTT opt-in, reconnect behavior
and installer lifecycle. `tests/ha_runtime_check.py` runs with the installed HA
Python against a staged component and starts no live services. Actual Mercedes
account access and end-to-end vehicle updates are cutover checks, not established
by mocked tests. Cloud API changes may require updating the pinned upstream maps.

## Blocked session recovery

Some Mercedes sessions keep returning WebSocket HTTP 429 even while token refresh
and the widget REST endpoint work. The widget can omit charging power, leaving
SoC and the local charger meter visible while vehicle charging power is unknown.
The upstream HA integration recovers this condition with an ordinary login.

By default this package stores no password and automatic recovery is disabled.
To opt in, stop dbus-ev and run the standalone login with an explicit private file:

```sh
svc -d /service/dbus-ev
# Wait for the worker to stop before taking ownership of the token file.
PYTHONPATH=/data/setupOptions/dbus-ev/python python3 -m dbus_ev.mercedes.auth \
  --region 'North America' \
  --credentials-file /data/setupOptions/dbus-ev/mercedes-credentials.json
```

Set `MERCEDES_CREDENTIALS_FILE` to that path in `local_config.py`, then start
`svc -u /service/dbus-ev`. The CLI saves username, password and region atomically
with mode 0600, separately from rotating tokens and outside the installed package.
Recovery rejects files accessible to other users, owned by another user, or for
another region. Keep the file out of release archives and MQTT.

Recovery follows the server's `Retry-After` and the minimum 30-minute global
cooldown; REST, config requests and token refresh also pause while waiting.
The existing OAuth owner attempts at most one automatic login per six hours,
with no hidden retries of individual login steps. Any failed attempt, including
2FA or new legal terms, disables further automatic login until a successful
standalone login. Pauses and login limits persist in `<token-file>.limits.json`,
outside the package. Restarting does not clear them. A successful manual login
clears the failure flag and reserves the next six hours from automatic login.
Resolve the account in the official app, wait for the server cooldown, run
standalone login, then restart the worker. Recovery never accepts terms or
sends vehicle commands. Clear `MERCEDES_CREDENTIALS_FILE` and restart to disable it.
