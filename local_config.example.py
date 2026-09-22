"""
Example configuration for dbus-ev.
Copy to local_config.py and fill in real values. NEVER commit local_config.py.
"""

# Home Assistant
# "mercedes": built-in client; "evcc": optional multi-brand engine; "ha": legacy reader.
DATA_SOURCE = "ha"
# Experimental providers are opt-in. See docs/vehicles.md for supported templates,
# private per-brand credentials, building the engine, and regional restrictions.
EVCC_BINARY = "/data/setupOptions/dbus-ev/bin/vehicle-engine"
EVCC_CONFIG_FILE = "/data/setupOptions/dbus-ev/vehicle.json"
EVCC_STATE_FILE = "/data/setupOptions/dbus-ev/vehicle-state.json"
EVCC_POLL_INTERVAL = 3600.0  # one read cycle/hour; minimum 30 min (BMW: 60 min)
EVCC_STALE_TIMEOUT = 7500.0  # repeated local reads do not renew the cache age
MERCEDES_VIN = ""
MERCEDES_REGION = "Europe"  # Europe, North America, Asia-Pacific, China
MERCEDES_TOKEN_FILE = "/data/setupOptions/dbus-ev/mercedes-token.json"
MERCEDES_STALE_TIMEOUT = 900.0  # 15 min; quiet-car REST fallback is at most every 10 min.
# Optional HTTP 429 recovery; create a private file with auth --credentials-file.
# Empty disables password storage and automatic login recovery.
MERCEDES_CREDENTIALS_FILE = ""
# Run python3 -m dbus_ev.mercedes.auth once to authorize. Never put tokens in this example.

# The unified process can also own the former dbus-evcharger identity.
# Stop/uninstall the old dbus-evcharger service before enabling this.
CHARGER_ENABLED = False
CHARGER_BUS_SUFFIX = "charger"
CHARGER_NAME = "EV Charger"
CHARGER_PHASES = 1
# Optional local Cerbo acload meter. No round trip through Home Assistant.
CERBO_METER_INSTANCE = None
CERBO_METER_TTL = 15.0
# Home charger association uses coordinates, never "charging active" as presence.
HOME_LATITUDE = None
HOME_LONGITUDE = None
HOME_RADIUS_METERS = 150.0

# Publish vehicle snapshots via Cerbo MQTT. Mercedes retains its HA integration;
# other brands publish raw JSON only. No HA discovery or automatic sensors.
# Off for fresh installations. SetupHelper: ./setup install --ha-mqtt=on|off
HA_MQTT_ENABLED = False
CERBO_MQTT_HOST = "127.0.0.1"
CERBO_MQTT_PORT = 1883
CERBO_PORTAL_ID = ""
CERBO_MQTT_USERNAME = ""
CERBO_MQTT_PASSWORD = ""

HA_URL = "http://192.168.1.50:8123"
HA_TOKEN = "your_long_lived_access_token_here"

# HA entities for EV
HA_SOC_ENTITY = "sensor.ev_soc"
HA_TARGET_SOC_ENTITY = "sensor.ev_target_soc"
HA_VIN_ENTITY = "sensor.ev_vin"
HA_BATTERY_CAPACITY_ENTITY = "sensor.ev_battery_capacity"
HA_CHARGING_STATE_ENTITY = "sensor.ev_charging_state"
HA_ODOMETER_ENTITY = "sensor.ev_odometer"
HA_RANGE_TO_GO_ENTITY = "sensor.ev_range_to_go"
HA_LATITUDE_ENTITY = "sensor.ev_latitude"
HA_LONGITUDE_ENTITY = "sensor.ev_longitude"
HA_AT_SITE_ENTITY = "binary_sensor.ev_at_site"
# Charging power entity (kW, from AC/Power). If your sensor reports kW the
# service will auto-convert to W for the D-Bus /Ac/Power path.
HA_POWER_ENTITY = "sensor.ev_charging_power"
HA_CURRENT_ENTITY = ""

# D-Bus instance (verify no collision on the GX)
DEVICE_INSTANCE = 0

# EVCS instance this vehicle is plugged into (matches dbus-evcharger DEVICE_INSTANCE)
EVCHARGER_INSTANCE = 40

# Textual bus-name suffix (D-Bus forbids digits after the last dot)
BUS_SUFFIX = "ha"

# Product identification (shown in Venus OS GUI)
PRODUCT_NAME = "My EV"
PRODUCT_ID = 0x1234

# Polling
POLL_INTERVAL = 15.0
SENSOR_STALE_TIMEOUT = 15.0
