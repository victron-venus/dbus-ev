# Venus OS D-Bus exporter for the VEHICLE

This service exports vehicle (EV) data from Home Assistant to the Venus OS
D-Bus service under the **standard EV charger bus name** so the VRM Portal
recognises it (bus-name prefix is what VRM uses to classify devices):

    com.victronenergy.evcharger.<N>

The dot-separated form is the same one `dbus-evcharger` uses. The previous
bus name `com.victronenergy.ev<N>` (no dot) was invisible to VRM.

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

Vehicle-specific paths (project extension, not part of the evcharger
standard):

- `/Soc` - State of charge (%)
- `/TargetSoc` - Target state of charge (%)
- `/VIN` - Vehicle identification number
- `/BatteryCapacity` - Battery capacity (kWh)
- `/ChargingState` - Raw HA charging_status string (e.g. "3")
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
