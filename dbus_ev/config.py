"""Configuration.

Real values live in local_config.py at the repo root (gitignored).
Falls back to safe defaults when it is missing.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

SETUP_OPTIONS_FILE = os.environ.get(
    "DBUS_EV_SETUP_OPTIONS", "/data/setupOptions/dbus-ev/options.json"
)
try:
    with open(SETUP_OPTIONS_FILE, encoding="utf-8") as options_file:
        _setup_options = json.load(options_file)
except FileNotFoundError:
    _setup_options = {}


try:
    import local_config  # type: ignore
except ImportError:
    local_config = None  # type: ignore
    logger.warning("local_config.py not found - using defaults/example values")


def _get(name: str, default):
    if name == "HA_MQTT_ENABLED" and name in _setup_options:
        return _setup_options[name]
    if local_config is not None and hasattr(local_config, name):
        return getattr(local_config, name)
    return default


def _read_version() -> str:
    try:
        with open(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "version"),
            encoding="utf-8",
        ) as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


# --- Home Assistant -----------------------------------------------------------
HA_URL: str = str(_get("HA_URL", "")).rstrip("/")
HA_TOKEN: str = str(_get("HA_TOKEN", ""))
HA_SOC_ENTITY: str = str(_get("HA_SOC_ENTITY", ""))
HA_TARGET_SOC_ENTITY: str = str(_get("HA_TARGET_SOC_ENTITY", ""))
HA_VIN_ENTITY: str = str(_get("HA_VIN_ENTITY", ""))
HA_BATTERY_CAPACITY_ENTITY: str = str(_get("HA_BATTERY_CAPACITY_ENTITY", ""))
HA_CHARGING_STATE_ENTITY: str = str(_get("HA_CHARGING_STATE_ENTITY", ""))
HA_ODOMETER_ENTITY: str = str(_get("HA_ODOMETER_ENTITY", ""))
HA_RANGE_TO_GO_ENTITY: str = str(_get("HA_RANGE_TO_GO_ENTITY", ""))
HA_LATITUDE_ENTITY: str = str(_get("HA_LATITUDE_ENTITY", ""))
HA_LONGITUDE_ENTITY: str = str(_get("HA_LONGITUDE_ENTITY", ""))
HA_AT_SITE_ENTITY: str = str(_get("HA_AT_SITE_ENTITY", ""))
HA_POWER_ENTITY: str = str(_get("HA_POWER_ENTITY", ""))
HA_CURRENT_ENTITY: str = str(_get("HA_CURRENT_ENTITY", ""))

# --- D-Bus identity -----------------------------------------------------------
DEVICE_INSTANCE: int = int(_get("DEVICE_INSTANCE", 22))
PRODUCT_NAME: str = str(_get("PRODUCT_NAME", "dbus-ev"))
PRODUCT_ID: int = int(_get("PRODUCT_ID", 0))
SOFTWARE_VERSION = _read_version()
# Instance of the EVCS (dbus-evcharger) the vehicle is plugged into.
# Exposed via /Mgmt/Connection as "evcharger:<n>" per the Venus dbus wiki.
EVCHARGER_INSTANCE: int = int(_get("EVCHARGER_INSTANCE", 40))
# Textual bus-name suffix (D-Bus forbids digits after the last dot).
BUS_SUFFIX: str = str(_get("BUS_SUFFIX", "ha"))

# --- Control logic ------------------------------------------------------------
# Master switch for automated actuation. Defaults to OFF so a fresh deploy is
# inert until thresholds have been tuned on site (fail-safe).
ENABLE_CONTROL: bool = bool(_get("ENABLE_CONTROL", False))
# Not used in EV service, but kept for compatibility with App structure
VALVE_START_VALUE: float = float(_get("VALVE_START_VALUE", 30.0))  # open below this %
VALVE_STOP_VALUE: float = float(_get("VALVE_STOP_VALUE", 85.0))  # close at/above this %
SENSOR_STALE_TIMEOUT: float = float(_get("SENSOR_STALE_TIMEOUT", 120.0))  # s
MIN_SWITCH_INTERVAL: float = float(_get("MIN_SWITCH_INTERVAL", 60.0))  # s
POLL_INTERVAL: float = float(_get("POLL_INTERVAL", 15.0))  # s

HEARTBEAT_FILE = "/run/dbus-ev/heartbeat"
HA_TIMEOUT: float = float(_get("HA_TIMEOUT", 3.0))

# One upstream provider per process; no automatic cloud/HA switching.
DATA_SOURCE: str = str(_get("DATA_SOURCE", "ha")).lower()
MERCEDES_VIN: str = str(_get("MERCEDES_VIN", "")).upper()
MERCEDES_REGION: str = str(_get("MERCEDES_REGION", "Europe"))
MERCEDES_TOKEN_FILE: str = str(
    _get("MERCEDES_TOKEN_FILE", "/data/setupOptions/dbus-ev/mercedes-token.json")
)
MERCEDES_STALE_TIMEOUT: float = float(_get("MERCEDES_STALE_TIMEOUT", 300.0))
HOME_LATITUDE = _get("HOME_LATITUDE", None)
HOME_LONGITUDE = _get("HOME_LONGITUDE", None)
HOME_RADIUS_METERS = float(_get("HOME_RADIUS_METERS", 150.0))

CHARGER_ENABLED: bool = bool(_get("CHARGER_ENABLED", False))
CHARGER_BUS_SUFFIX: str = str(_get("CHARGER_BUS_SUFFIX", "charger"))
CHARGER_NAME: str = str(_get("CHARGER_NAME", "EV Charger"))
CHARGER_PHASES: int = int(_get("CHARGER_PHASES", 1))
CERBO_METER_INSTANCE = _get("CERBO_METER_INSTANCE", None)
CERBO_METER_TTL = float(_get("CERBO_METER_TTL", 15.0))
HA_MQTT_ENABLED: bool = bool(_get("HA_MQTT_ENABLED", False))
CERBO_MQTT_HOST = str(_get("CERBO_MQTT_HOST", "127.0.0.1"))
CERBO_MQTT_PORT = int(_get("CERBO_MQTT_PORT", 1883))
CERBO_MQTT_USERNAME = str(_get("CERBO_MQTT_USERNAME", ""))
CERBO_MQTT_PASSWORD = str(_get("CERBO_MQTT_PASSWORD", ""))
CERBO_PORTAL_ID = str(_get("CERBO_PORTAL_ID", ""))

# Battery capacity in kWh (kWh). Optional: when unset, /BatteryCapacity is
# not published.
BATTERY_CAPACITY_KWH: float | None = _get("BATTERY_CAPACITY_KWH", None)
if BATTERY_CAPACITY_KWH is not None:
    BATTERY_CAPACITY_KWH = float(BATTERY_CAPACITY_KWH)

# Circuit breaker
CIRCUIT_OPEN_THRESHOLD: int = int(_get("CIRCUIT_OPEN_THRESHOLD", 5))
CIRCUIT_RESET_TIMEOUT: float = float(_get("CIRCUIT_RESET_TIMEOUT", 60.0))


def control_enabled() -> bool:
    """Automation runs only with ENABLE_CONTROL and a configured token."""
    if not HA_TOKEN or HA_TOKEN == "your_long_lived_access_token_here":
        return False
    return ENABLE_CONTROL
