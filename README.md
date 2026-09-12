# Venus OS D-Bus exporter for the VEHICLE

This service exports vehicle data from Home Assistant as
`com.victronenergy.ev.<suffix>` (by default `com.victronenergy.ev.ha`).
The numeric identifier belongs in `/DeviceInstance`; the service suffix is a
textual identifier. The separate `dbus-evcharger` package exports charger data.

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

Copy `local_config.example.py` to `local_config.py` and set the Home Assistant URL, long-lived access token, and entity IDs for the vehicle data.

## Usage

Run the service on the Cerbo GX (or any Venus OS device) with Python 3.11+.

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

Service definitions persist under `/data/dbus-ev/service/dbus-ev`.
`/service/dbus-ev` is a symlink recreated by `/data/rc.local`, including
when that script already ends with `exit 0`. The logger recreates its volatile
`/var/log/dbus-ev` directory and rotates four 25 KB files. Heartbeats
also live on volatile storage. Runtime data does not require writes to the
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

`deploy.sh` fails if a fresh heartbeat does not appear within 60 seconds or the
service never reaches `up`. A heartbeat proves the loop is running, not that
Home Assistant is reachable: also inspect `/Connected` and the log. Restore a
previous release with its `update.sh`, keeping the device-local configuration.
The isolated installer regression test covers two consecutive in-place updates,
configuration preservation, service symlinks, and a boot script ending in `exit 0`.


### VRM capacity contract

Venus OS v3.75 rounds `/BatteryCapacity` when uploading EV configuration. A
string such as `"118"` causes `vrmlogger` to restart with `TypeError`. The bridge
normalizes numeric configuration strings (including `"118.5"`) to floats and
publishes invalid, infinite or negative values as unavailable. Capacity selection
prefers the HA sensor, then a numeric `HA_BATTERY_CAPACITY_ENTITY` literal, then
`BATTERY_CAPACITY_KWH`. `/Connected` becomes zero when HA data expires.
