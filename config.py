"""Configuration for dbus-ev."""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Polling --------------------------------------------------------------
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "5.0"))
SENSOR_STALE_TIMEOUT = float(os.getenv("SENSOR_STALE_TIMEOUT", "15.0"))

# --- Home Assistant -------------------------------------------------------
HA_URL = os.getenv("HA_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# --- EV Entities (adjust to your setup) -----------------------------------
HA_SOC_ENTITY = os.getenv("HA_SOC_ENTITY", "sensor.mercedes_soc")
HA_TARGET_SOC_ENTITY = os.getenv("HA_TARGET_SOC_ENTITY", "sensor.mercedes_target_soc")
HA_VIN_ENTITY = os.getenv("HA_VIN_ENTITY", "sensor.mercedes_vin")
HA_BATTERY_CAPACITY_ENTITY = os.getenv(
    "HA_BATTERY_CAPACITY_ENTITY", "sensor.mercedes_battery_capacity"
)
HA_CHARGING_STATE_ENTITY = os.getenv("HA_CHARGING_STATE_ENTITY", "sensor.mercedes_charging_state")
HA_ODOMETER_ENTITY = os.getenv("HA_ODOMETER_ENTITY", "sensor.mercedes_odometer")
HA_RANGE_TO_GO_ENTITY = os.getenv("HA_RANGE_TO_GO_ENTITY", "sensor.mercedes_range_to_go")
HA_LATITUDE_ENTITY = os.getenv("HA_LATITUDE_ENTITY", "sensor.mercedes_latitude")
HA_LONGITUDE_ENTITY = os.getenv("HA_LONGITUDE_ENTITY", "sensor.mercedes_longitude")
HA_AT_SITE_ENTITY = os.getenv("HA_AT_SITE_ENTITY", "binary_sensor.mercedes_at_site")

# --- Device instance ------------------------------------------------------
# Set via local_config.py or environment
DEVICE_INSTANCE = int(os.getenv("DEVICE_INSTANCE", "0"))

# --- Software -------------------------------------------------------------
SOFTWARE_VERSION = "0.0.0"  # overridden by version file
