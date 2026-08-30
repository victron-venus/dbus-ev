"""Configuration.

Real values live in local_config.py at the repo root (gitignored).
Falls back to safe defaults when it is missing.
"""

import logging
import os

logger = logging.getLogger(__name__)


try:
    import local_config  # type: ignore
except ImportError:
    local_config = None  # type: ignore
    logger.warning("local_config.py not found - using defaults/example values")


def _get(name: str, default):
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
