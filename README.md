# Venus OS D-Bus exporter for the VEHICLE

This service exports vehicle (EV) data from Home Assistant to the Venus OS D-Bus service under `com.victronenergy.ev`.

## Exported properties

- `/Soc` - State of charge (%)
- `/TargetSoc` - Target state of charge (%)
- `/VIN` - Vehicle identification number
- `/BatteryCapacity` - Battery capacity (kWh)
- `/ChargingState` - Charging state (string)
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
