"""
Example configuration for dbus-ev.
Copy to local_config.py and fill in real values. NEVER commit local_config.py.
"""

# Home Assistant
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
