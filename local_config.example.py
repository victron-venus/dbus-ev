"""
Example configuration for dbus-ev.
Copy to local_config.py and fill in real values. NEVER commit local_config.py.
"""

# Home Assistant
# Select "mercedes" for direct cloud telemetry; "ha" preserves the existing reader.
DATA_SOURCE = "ha"
MERCEDES_VIN = ""
MERCEDES_REGION = "Europe"  # Europe, North America, Asia-Pacific, China
MERCEDES_TOKEN_FILE = "/data/setupOptions/dbus-ev/mercedes-token.json"
MERCEDES_STALE_TIMEOUT = 300.0
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

# Publish Mercedes snapshots for the accompanying HA integration via Cerbo MQTT.
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
