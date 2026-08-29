# Copy to local_config.py and fill in real values. NEVER commit local_config.py.

# Home Assistant
HA_URL = "http://192.168.1.50:8123"
HA_TOKEN = "your_long_lived_access_token_here"

# HA entities for EV
HA_SOC_ENTITY = "sensor.mercedes_soc"
HA_TARGET_SOC_ENTITY = "sensor.mercedes_target_soc"
HA_VIN_ENTITY = "sensor.mercedes_vin"
HA_BATTERY_CAPACITY_ENTITY = "sensor.mercedes_battery_capacity"
HA_CHARGING_STATE_ENTITY = "sensor.mercedes_charging_state"
HA_ODOMETER_ENTITY = "sensor.mercedes_odometer"
HA_RANGE_TO_GO_ENTITY = "sensor.mercedes_range_to_go"
HA_LATITUDE_ENTITY = "sensor.mercedes_latitude"
HA_LONGITUDE_ENTITY = "sensor.mercedes_longitude"
HA_AT_SITE_ENTITY = "binary_sensor.mercedes_at_site"

# D-Bus instance (verify no collision on the GX)
DEVICE_INSTANCE = 0

# Product identification (shown in Venus OS GUI)
PRODUCT_NAME = "Mercedes EV"
PRODUCT_ID = 0x1234

# Polling
POLL_INTERVAL = 5.0
SENSOR_STALE_TIMEOUT = 15.0
