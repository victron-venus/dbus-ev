# Venus OS vehicle and charger bridge

Optional experimental multi-brand providers are documented in [docs/vehicles.md](docs/vehicles.md). They reuse pinned evcc vehicle libraries, publish raw MQTT only (no automatic HA sensors), and require a separately built optional engine.

This service exports vehicle data from Mercedes or Home Assistant as
`com.victronenergy.ev.<suffix>` (by default `com.victronenergy.ev.ha`).
The numeric identifier belongs in `/DeviceInstance`; the service suffix is a
textual identifier. With `DATA_SOURCE = "mercedes"`, this package connects directly
to Mercedes using one OAuth session and one WebSocket, and can also own the
`com.victronenergy.evcharger.charger` service formerly provided by `dbus-evcharger`.

Set `HA_MQTT_ENABLED = True` to publish complete Mercedes telemetry for the
included [Home Assistant MQTT adapter](ha/README.md). The example defaults to
`False`. Both `local_config.py` and SetupHelper installation options are supported:
`./setup install --ha-mqtt=on` (or `off`). PackageManager reinstalls reuse the
saved choice under `/data/setupOptions/dbus-ev/options.json`; interactive terminal
installs also offer the choice. A saved SetupHelper choice overrides the config
file until changed or that override is removed.

Read [migration and rollback](docs/mercedes-migration.md) before switching a live
installation. The old HA integration must stop before the direct Mercedes client
starts. Preserve the two existing D-Bus identities; remove the old charger worker.

### Direct Mercedes backend

Provision the optional dependencies with `./install-mercedes-deps.sh` on Venus,
or `uv sync --extra mercedes --extra dev` for development. On Venus, optional
packages live in `/data/setupOptions/dbus-ev/python`; system packages are unchanged.
The updater checks dependencies before stopping any service. Authorize once:

```sh
cd /data/dbus-ev
PYTHONPATH=/data/setupOptions/dbus-ev/python python3 -m dbus_ev.mercedes.auth --region 'North America'
```

By default, standalone login stores only tokens and device identity. Optional
[blocked-session recovery](docs/mercedes-migration.md#blocked-session-recovery)
can retain private login credentials when explicitly configured.
An existing HA token can also be transferred as described in the migration guide.
Regions use the same mobile API as mbapi2020. The inherited username/password flow
does not support accounts requiring 2FA; accept changed legal terms in the official
Mercedes app. No terms are accepted automatically. The separate China PIN login
is not exposed by this release's standalone CLI.

Configure VIN, region, battery capacity and (for charger association) home
coordinates. With `CHARGER_ENABLED = True`, instance 40 and suffix `charger` remain
the defaults. `CERBO_METER_INSTANCE` optionally reads power directly from an
`acload` service through the same local MQTT client. A dedicated circuit above
50 W establishes local charging; at zero power, vehicle location/status determine
connection when available. Unknown state and missing readings remain unavailable.
Daily energy is never substituted for lifetime or session energy.

When Mercedes explicitly reports the charge cable unplugged but omits charging
power, the vehicle D-Bus service reports 0 W. Other missing or invalid power values
remain unknown. Original Mercedes attributes forwarded to HA are unchanged.

Mercedes field timestamps travel unchanged. Re-reading the local cache cannot
renew its acquisition time. `MERCEDES_STALE_TIMEOUT` defaults to 900 seconds and
controls direct-provider availability. The MQTT last will reports process/broker
loss; the HA receiver also expires retained data independently. A single token-file
lock prevents two local clients from sharing that authorization state.

Cloud access is push-first: quiet-car REST fallback runs at most every ten
minutes. Any HTTP 429 pauses new requests across all Mercedes endpoints for at
least 30 minutes, with increasing backoff and full `Retry-After` support.
Optional automatic login is limited to once per six hours. These limits survive
restarts; see [request policy and upgrade settings](docs/mercedes-upstream.md).

The HA backend remains selectable as `DATA_SOURCE = "ha"`. Existing standalone
charger HA/MQTT installations may keep using `dbus-evcharger` until migrated;
enabling the integrated charger requires the Mercedes backend.

## Python runtime

Native Venus OS packages target **Python 3.12.x**. The audited Cerbo on Venus OS
v3.75 reports Python **3.12.13**; the [official Venus OS v3.79 manifest](https://updates.victronenergy.com/feeds/venus/release/sdk/venus-scarthgap-x86_64-arm-cortexa8hf-neon-toolchain-v3.79.target.manifest)
also ships 3.12.13. Local development and CI use `.python-version` / Python
3.12.13. Package metadata accepts 3.12 patch updates and rejects other minor
versions until they have been validated. Use the firmware's system interpreter
and its matching D-Bus/GI libraries on the device; do not replace the OS Python.

<!-- ci-release-process:start -->
## Release process

See the [release strategy](RELEASING.md) for validation, nightly, beta, RC and stable promotion rules, and the [operator runbook](docs/release-workflow.md) for local commands.
<!-- ci-release-process:end -->

## Exported properties

Standard EV charger paths (required for VRM dashboard rendering):

- `/Status` - int (0=disconnected, 1=connected, 2=charging, 3=charged, 4=waiting_for_sun)
- `/Ac/Power` - W (vehicle-side AC power)
- `/Ac/L1/Power` - W (single-phase)
- `/Ac/L1/Voltage` - V
- `/Ac/L1/Current` - A
- `/Ac/Energy/Forward` - kWh
- `/Current` - A
- `/SetCurrent` - A setpoint (read-only here)
- `/NrOfPhases` - 1
- `/Position` - 0 (AC Output)
- `/PositionIsAdjustable` - 0
- `/IsGenericEnergyMeter` - 0

Standard vehicle paths:

- `/Soc` - State of charge (%)
- `/TargetSoc` - Target state of charge (%)
- `/VIN` - Vehicle identification number
- `/BatteryCapacity` - finite numeric battery capacity in kWh, or an invalid value if unavailable
- `/ChargingState` - int (Venus wiki enum: 0=Not charging, 3=Charging, 250=Blocked, 255=Unavailable, 256=Discharging, 244=Sustain, etc.)
- `/Odometer` - Odometer (km)
- `/RangeToGo` - Range to go (km)
- `/Position/Latitude` - Latitude (degrees)
- `/Position/Longitude` - Longitude (degrees)
- `/AtSite` - At site (boolean)

Standard D-Bus properties are also provided:
- `/DeviceInstance`
- `/ProductName`
- `/ProductId`
- `/Mgmt/ProcessName`
- `/Mgmt/ProcessVersion`
- `/Mgmt/Connection`

## Configuration

Copy `local_config.example.py` to `local_config.py` and select `DATA_SOURCE`. For
Mercedes, configure the VIN, region and token file as described above; enable the
integrated charger and HA MQTT publication as needed. For the HA backend, set the
Home Assistant URL, long-lived access token and vehicle entity IDs.

## Usage

Run the service on the Cerbo GX (or any Venus OS device) with Python 3.12.x.

The service uses the `vedbus` package which is available on Venus OS.

## License

MIT

## HA charging state mapping

The Home Assistant `mbapi2020` integration reports its charging status as a
numeric state string (`CHARGINGSTATUS` enum). This enum is **inverted** relative
to the Venus OS D-Bus wiki definition for `/ChargingState`:

| mbapi2020 value | mbapi2020 label | Venus wiki `/ChargingState` |
|---|---|---|
| 0 | CHARGINGSTATUS_CHARGING | 3 (Charging) |
| 1 | CHARGINGSTATUS_END_OF_CHARGE | 244 (Sustain) |
| 2 | CHARGINGSTATUS_CHARGE_BREAK | 250 (Blocked) |
| 3 | CHARGINGSTATUS_CHARGE_CABLE_UNPLUGGED | 0 (Not charging) |
| 4 | CHARGINGSTATUS_CHARGING_ERROR | 255 (Unavailable) |
| 5 | CHARGINGSTATUS_SLOW_CHARGING | 3 (Charging) |
| 6 | CHARGINGSTATUS_FAST_CHARGING | 3 (Charging) |
| 7 | CHARGINGSTATUS_DISCHARGING | 256 (Discharging) |
| 8 | CHARGINGSTATUS_NO_CHARGING | 0 (Not charging) |
| 9 | CHARGINGSTATUS_SLOW_CHARGING_AFTER_REACHING_TRIP_TARGET | 3 (Charging) |
| 10 | CHARGINGSTATUS_CHARGING_AFTER_REACHING_TRIP_TARGET | 3 (Charging) |
| 11 | CHARGINGSTATUS_FAST_CHARGING_AFTER_REACHING_TRIP_TARGET | 3 (Charging) |
| 12 | CHARGINGSTATUS_COMMUNICATION_WITH_EVSE_ACTIVE_NO_ENERGY_FLOW | 244 (Sustain) |
| 13 | CHARGINGSTATUS_AC_CHARGING_ACTIVE | 3 (Charging) |
| 14 | CHARGINGSTATUS_DC_CHARGING_ACTIVE | 3 (Charging) |
| 15 | CHARGINGSTATUS_SOH_BATTERY_CALIBRATION_ACTIVE | 244 (Sustain) |
| 16 | CHARGINGSTATUS_UNKNOWN | 255 (Unavailable) |

The service translates mbapi2020 numeric strings to Venus wiki enum integers so
the VRM dashboard shows semantically correct labels.

## Install

Via SetupHelper PackageManager (GUI v1): drop the repo in `/data/dbus-ev`
(must contain `version` + `setup`). Then Settings → PackageManager → install,
or:

```sh
/data/dbus-ev/setup install
/data/dbus-ev/setup uninstall
```

`gitHubInfo` is `victron-venus:latest`. Device-local `local_config.py` is not overwritten.

```sh
./deploy.sh          # streams repo to Cerbo, runs update.sh there
./restart.sh         # restart the service only
ssh cerbo 'tail -f /var/log/dbus-ev/current'
```


## Venus OS installation and recovery

Use the canonical `/data/dbus-ev` directory. Both `setup install`
(SetupHelper/PackageManager) and the workstation `deploy.sh` call `update.sh`.
A release is staged under volatile `/tmp` before stopping the service, so
reinstalling from the installed tree does not delete the update source.
The updater preserves `local_config.py`; `deploy.sh` deliberately replaces it
when the workstation has a local copy (`PUSH_LOCAL_CONFIG=1`).
Existing service and log directory inodes, ownership, supervisor state and the
canonical `/service` symlink are preserved. Only the application is stopped;
run scripts are replaced atomically and a healthy logger keeps running.
Ordinary updates do not restart PackageManager. A stuck application receives
one supervisor-scoped kill after twenty seconds; installation aborts if it is
still running after twenty-five seconds. Unexpected service links, real `/service`
directories or legacy firmware copies require a separate migration before
updating; the updater leaves them untouched.

Service definitions persist under `/data/dbus-ev/service/dbus-ev`.
`/service/dbus-ev` is a symlink recreated by `/data/rc.local`, including
when that script already ends with `exit 0`. The logger creates
`/var/log/dbus-ev` and uses bounded `multilog` rotation (`s25000 n4`).
On the audited Venus OS image, `/var/log` resolves to persistent `/data/log`,
so these logs write flash. Heartbeats live in volatile `/run` storage.
Runtime data does not require writes to the
read-only firmware filesystem. Firmware updates can replace system Python
packages; check dependencies after each update before assuming the service is
healthy. The installer does not run `pip` or upgrade system packages.

Before installation, check the target interpreter:

```sh
python3 --version
python3 -c "import requests, dbus; from gi.repository import GLib"
```

Verify a running process and its D-Bus data after installation:

```sh
svstat /service/dbus-ev /service/dbus-ev/log
readlink /service/dbus-ev
tail -n 40 /var/log/dbus-ev/current
```

`update.sh` confirms termination before copying but does not wait for a fresh
process or heartbeat after requesting startup. The deployment caller must
verify startup and D-Bus availability.

`deploy.sh` fails if a fresh heartbeat does not appear within 60 seconds or the
service never reaches `up`. A heartbeat proves the loop is running, not that
Home Assistant is reachable: also inspect `/Connected` and the log. Restore a
previous release with its `update.sh`, keeping the device-local configuration.
Installer regressions cover repeated updates with live directory handles,
supervisor-state and ownership preservation, atomic run-script replacement,
configuration, safe rejection before stopping, and boot hooks before `exit 0`.


### VRM capacity contract

Venus OS v3.75 rounds `/BatteryCapacity` when uploading EV configuration. A
string such as `"118"` causes `vrmlogger` to restart with `TypeError`. The bridge
normalizes numeric configuration strings (including `"118.5"`) to floats and
publishes invalid, infinite or negative values as unavailable. Capacity selection
prefers the HA sensor, then a numeric `HA_BATTERY_CAPACITY_ENTITY` literal, then
`BATTERY_CAPACITY_KWH`. `/Connected` becomes zero when HA data expires.

### HA responsiveness and validity

The service runs one HA request at a time in a dedicated worker. D-Bus exports,
freshness checks and heartbeat updates stay on the GLib main loop; a slow HA
request cannot queue additional polls or freeze reads of `/Connected`. Completed
snapshots are applied only on that main loop. Shutdown closes the HTTP session
after its active request completes, and discards pending publication callbacks.
Freshness starts at monotonic request acquisition time, not callback delivery;
a request or queued result older than the configured timeout cannot renew it.

Power and distance units are included in the same template request as their
values. The existing W/kW and miles/km conversions are preserved, including the
legacy kW default when power units are absent. There are no separate attribute
HTTP requests. Non-finite numeric readings are unavailable; unknown charging
states map to the unavailable enum instead of reaching an integer conversion.
Invalid power clears both published power paths rather than retaining an older
measurement. A measured zero remains zero.

`SENSOR_STALE_TIMEOUT` still controls `/Connected` (120 seconds by default).
Consumers must honor that flag when using last-known vehicle data. A successful
HA reply proves receipt from HA, not independent freshness of a vehicle's
upstream integration. Local regressions cover a blocked request, continued main
loop ticks, expiry, single outstanding work item, recovery and safe shutdown.
