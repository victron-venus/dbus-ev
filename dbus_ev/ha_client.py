"""Home Assistant REST client for EV.

Reads EV entities through one batched /api/template call and serves
last-known values while HA is unreachable, guarded by a circuit breaker.
"""

import json
import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Jinja template sent to /api/template. Tokens are replaced literally.
# Use ternary operator (x if cond else y) inside {{ }} — Jinja2 doesn't allow
# bare {% if %} blocks inside expression delimiters.
# VIN: @VIN_ENTITY@ replaced with entity id or empty (entity check).
# @VIN_VALUE@ replaced with literal JSON string or empty (static value).
TEMPLATE_BODY = """{{ {
  "soc": states('@SOC@') | string,
  "target_soc": states('@TARGET_SOC@') | string if '@TARGET_SOC@' != '' else none,
  "vin": states('@VIN_ENTITY@') | string if '@VIN_ENTITY@' != '' else '@VIN_VALUE@',
  "battery_capacity": states('@BATTERY_CAPACITY@') | string if '@BATTERY_CAPACITY@' != '' else none,
  "charging_state": states('@CHARGING_STATE@') | string if '@CHARGING_STATE@' != '' else none,
  "odometer": states('@ODOMETER@') | string if '@ODOMETER@' != '' else none,
  "range_to_go": states('@RANGE_TO_GO@') | string if '@RANGE_TO_GO@' != '' else none,
  "latitude": states('@LATITUDE@') | string if '@LATITUDE@' != '' else none,
  "longitude": states('@LONGITUDE@') | string if '@LONGITUDE@' != '' else none,
  "at_site": states('@AT_SITE@') | string if '@AT_SITE@' != '' else none,
  "current": states('@CURRENT@') | string if '@CURRENT@' != '' else none,
  "power": states('@POWER@') | string if '@POWER@' != '' else none
} | to_json }}"""


class HomeAssistantError(Exception):
    """Base class for HA client errors."""


class HomeAssistantAPIError(HomeAssistantError):
    """Raised when HA returns a non-2xx response to /api/template."""


class CircuitBreaker:
    """Opens after `threshold` consecutive failures; retries after reset_timeout s."""

    def __init__(self, threshold: int = 5, reset_timeout: float = 60.0) -> None:
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            # Half-open: allow one attempt through.
            logger.info("Circuit breaker half-open, allowing retry")
            self._opened_at = None
            self._failures = self.threshold - 1  # one more failure re-opens
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._opened_at is None and self._failures >= self.threshold:
            self._opened_at = time.monotonic()
            logger.warning("Circuit breaker OPEN after %i consecutive failures", self._failures)


def state_is_on(state: Any) -> bool | None:
    """Map an HA state string to on/off. unavailable/unknown -> None."""
    s = str(state).strip().lower() if state is not None else ""
    if s in ("unavailable", "unknown", "", "none"):
        return None
    return s in ("on", "true", "yes")


def _is_ha_entity(value: str) -> bool:
    """Return True if value looks like an HA entity id (domain.object_id)."""
    return bool(value) and "." in value


# HA charging-state strings -> Victron /ChargingState enum.
#
# The mbapi2020 integration (custom_components/mbapi2020) delivers its
# CHARGINGSTATUS enum as a numeric state string. That enum is INVERTED
# relative to the Venus wiki: mbapi2020's "0" = Charging, "3" = Unplugged,
# while Venus wiki's "0" = Not charging, "3" = Charging. We translate
# mbapi2020 values to Venus wiki values so /ChargingState is semantically
# correct on the D-Bus side.
#
# Full mapping (mbapi2020 CHARGINGSTATUS -> Venus wiki /ChargingState):
#   0  CHARGINGSTATUS_CHARGING                          -> 3    Charging
#   1  CHARGINGSTATUS_END_OF_CHARGE                      -> 244  Sustain
#   2  CHARGINGSTATUS_CHARGE_BREAK                       -> 250  Blocked
#   3  CHARGINGSTATUS_CHARGE_CABLE_UNPLUGGED             -> 0    Not charging
#   4  CHARGINGSTATUS_CHARGING_ERROR                     -> 255  Unavailable
#   5  CHARGINGSTATUS_SLOW_CHARGING                      -> 3    Charging
#   6  CHARGINGSTATUS_FAST_CHARGING                      -> 3    Charging
#   7  CHARGINGSTATUS_DISCHARGING                        -> 256  Discharging
#   8  CHARGINGSTATUS_NO_CHARGING                        -> 0    Not charging
#   9  CHARGINGSTATUS_SLOW_CHARGING_AFTER_REACHING...    -> 3    Charging
#  10  CHARGINGSTATUS_CHARGING_AFTER_REACHING...         -> 3    Charging
#  11  CHARGINGSTATUS_FAST_CHARGING_AFTER_REACHING...    -> 3    Charging
#  12  CHARGINGSTATUS_COMMUNICATION_WITH_EVSE_ACTIVE...  -> 244  Sustain
#  13  CHARGINGSTATUS_AC_CHARGING_ACTIVE                 -> 3    Charging
#  14  CHARGINGSTATUS_DC_CHARGING_ACTIVE                 -> 3    Charging
#  15  CHARGINGSTATUS_SOH_BATTERY_CALIBRATION_ACTIVE     -> 244  Sustain
#  16  CHARGINGSTATUS_UNKNOWN                            -> 255  Unavailable
_CHARGING_STATE_MAP: dict[str, int] = {
    "0": 3,  # mbapi2020 CHARGING -> Venus Charging
    "1": 244,  # mbapi2020 END_OF_CHARGE -> Venus Sustain
    "2": 250,  # mbapi2020 CHARGE_BREAK -> Venus Blocked
    "3": 0,  # mbapi2020 UNPLUGGED -> Venus Not charging
    "4": 255,  # mbapi2020 CHARGING_ERROR -> Venus Unavailable
    "5": 3,  # mbapi2020 SLOW_CHARGING -> Venus Charging
    "6": 3,  # mbapi2020 FAST_CHARGING -> Venus Charging
    "7": 256,  # mbapi2020 DISCHARGING -> Venus Discharging
    "8": 0,  # mbapi2020 NO_CHARGING -> Venus Not charging
    "9": 3,  # mbapi2020 SLOW_CHARGING_AFTER... -> Venus Charging
    "10": 3,  # mbapi2020 CHARGING_AFTER... -> Venus Charging
    "11": 3,  # mbapi2020 FAST_CHARGING_AFTER... -> Venus Charging
    "12": 244,  # mbapi2020 COMMUNICATION_NO_ENERGY -> Venus Sustain
    "13": 3,  # mbapi2020 AC_CHARGING_ACTIVE -> Venus Charging
    "14": 3,  # mbapi2020 DC_CHARGING_ACTIVE -> Venus Charging
    "15": 244,  # mbapi2020 SOH_CALIBRATION -> Venus Sustain
    "16": 255,  # mbapi2020 UNKNOWN -> Venus Unavailable
}


def map_charging_state(state: str | None) -> int | None:
    """Map an HA charging-state string to the Victron enum."""
    if state is None:
        return None
    key = state.strip().lower()
    if key in ("unavailable", "unknown"):
        return 255
    return _CHARGING_STATE_MAP.get(key, state)


def build_template(
    *,
    soc_entity: str,
    target_soc_entity: str,
    vin_entity: str,
    battery_capacity_entity: str,
    charging_state_entity: str,
    odometer_entity: str,
    range_to_go_entity: str,
    latitude_entity: str,
    longitude_entity: str,
    at_site_entity: str,
    current_entity: str,
    power_entity: str,
) -> str:
    # Static VIN: emit as Jinja string literal (no HA lookup).
    # Entity id: emit states() call (HA lookup).
    if _is_ha_entity(vin_entity):
        vin_entity_token = vin_entity
        vin_value_token = ""
    else:
        vin_entity_token = ""
        # Escape single quote (Jinja uses '' to escape) and backslash.
        vin_value_token = vin_entity.replace("\\", "\\\\").replace("'", "''") if vin_entity else ""
    return (
        TEMPLATE_BODY.replace("@SOC@", soc_entity)
        .replace("@TARGET_SOC@", target_soc_entity or "")
        .replace("@VIN_ENTITY@", vin_entity_token)
        .replace("@VIN_VALUE@", vin_value_token)
        .replace("@BATTERY_CAPACITY@", battery_capacity_entity or "")
        .replace("@CHARGING_STATE@", charging_state_entity or "")
        .replace("@ODOMETER@", odometer_entity or "")
        .replace("@RANGE_TO_GO@", range_to_go_entity or "")
        .replace("@LATITUDE@", latitude_entity or "")
        .replace("@LONGITUDE@", longitude_entity or "")
        .replace("@AT_SITE@", at_site_entity or "")
        .replace("@CURRENT@", current_entity or "")
        .replace("@POWER@", power_entity or "")
    )


class HaClient:
    """Batch-fetch EV entities from HA /api/template with last-known fallback."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        soc_entity: str,
        target_soc_entity: str,
        vin_entity: str,
        battery_capacity_entity: str,
        charging_state_entity: str,
        odometer_entity: str,
        range_to_go_entity: str,
        latitude_entity: str,
        longitude_entity: str,
        at_site_entity: str,
        current_entity: str,
        power_entity: str,
        timeout: float = 3.0,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.soc_entity = soc_entity
        self.target_soc_entity = target_soc_entity
        self.vin_entity = vin_entity
        self.battery_capacity_entity = battery_capacity_entity
        self.charging_state_entity = charging_state_entity
        self.odometer_entity = odometer_entity
        self.range_to_go_entity = range_to_go_entity
        self.latitude_entity = latitude_entity
        self.longitude_entity = longitude_entity
        self.at_site_entity = at_site_entity
        self.current_entity = current_entity
        self.power_entity = power_entity
        self.timeout = timeout
        self.breaker = breaker or CircuitBreaker()
        # Last-known-good snapshot, served while HA is unreachable.
        self.last_known: dict[str, Any] = {
            "soc": None,
            "target_soc": None,
            "vin": None,
            "battery_capacity": None,
            "charging_state": None,
            "odometer": None,
            "range_to_go": None,
            "latitude": None,
            "longitude": None,
            "at_site": None,
            "current": None,
            "power": None,
        }
        self._template = build_template(
            soc_entity=soc_entity,
            target_soc_entity=target_soc_entity,
            vin_entity=vin_entity,
            battery_capacity_entity=battery_capacity_entity,
            charging_state_entity=charging_state_entity,
            odometer_entity=odometer_entity,
            range_to_go_entity=range_to_go_entity,
            latitude_entity=latitude_entity,
            longitude_entity=longitude_entity,
            at_site_entity=at_site_entity,
            current_entity=current_entity,
            power_entity=power_entity,
        )
        self._configured = bool(base_url and token)
        self._session = requests.Session()
        if token:
            self._session.headers.update(
                {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            )
        self._last_error_log = 0.0

    def _get_entity_attributes(self, entity_id: str) -> dict[str, Any] | None:
        """Fetch attributes for a single entity, including unit_of_measurement."""
        if not entity_id:
            return None
        try:
            resp = self._session.get(
                f"{self.base_url}/api/states/{entity_id}",
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            data = json.loads(resp.text)
            return data.get("attributes", {})
        except (requests.exceptions.RequestException, json.JSONDecodeError):
            return None

    def _log_error_throttled(self, msg: str) -> None:
        now = time.monotonic()
        if now - self._last_error_log >= 60.0:
            self._last_error_log = now
            logger.error(msg)

    def _normalize_unit(
        self,
        value: float | None,
        entity: str,
        unit_map: dict[str, float],
        accepted: set[str],
    ) -> float | None:
        """Convert a numeric value from HA unit to Venus unit.

        Warns (publishing raw) when the entity's unit_of_measurement is neither
        in unit_map nor in accepted. HA reports power in kW; /Ac/Power is W.
        Odometer/range-to-go may be miles; wiki expects km.
        """
        if value is None or not entity:
            return value
        attrs = self._get_entity_attributes(entity) or {}
        u = str(attrs.get("unit_of_measurement", "")).lower()
        if u in unit_map:
            return value * unit_map[u]
        if u not in accepted:
            logger.warning("entity %s has unknown unit %r, publishing raw", entity, u)
        return value

    def poll(self) -> dict[str, Any]:
        """Fetch EV states.

        Returns a dictionary with keys: soc, target_soc, vin, battery_capacity,
        charging_state, odometer, range_to_go, latitude, longitude, at_site,
        each being float|string|bool|None, and 'ok': bool where ok=True means
        the values were fetched live on this call. On failure the last-known
        snapshot is returned with ok=False.
        """
        result = dict(self.last_known)
        result["ok"] = False
        if not self._configured:
            self._log_error_throttled("HA client not configured (HA_URL or HA_TOKEN empty)")
            return result
        if self.breaker.is_open:
            return result
        try:
            resp = self._session.post(
                f"{self.base_url}/api/template",
                json={"template": self._template},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise HomeAssistantAPIError(f"/api/template HTTP {resp.status_code}")
            data = json.loads(resp.text)

            # Helper to convert string to float or None
            def to_float(s: Any) -> float | None:
                if s is None:
                    return None
                s = str(s).strip()
                if s == "" or s.lower() in ("none", "unknown", "unavailable"):
                    return None
                try:
                    return float(s)
                except ValueError:
                    return None

            def to_str(s: Any) -> str | None:
                if s is None:
                    return None
                s = str(s).strip()
                if s == "" or s.lower() in ("none", "unknown", "unavailable"):
                    return None
                return s

            soc = to_float(data.get("soc"))
            target_soc = to_float(data.get("target_soc"))
            vin = to_str(data.get("vin"))
            battery_capacity = to_float(data.get("battery_capacity"))
            charging_state = map_charging_state(to_str(data.get("charging_state")))
            odometer = to_float(data.get("odometer"))
            range_to_go = to_float(data.get("range_to_go"))
            latitude = to_float(data.get("latitude"))
            longitude = to_float(data.get("longitude"))
            at_site = state_is_on(data.get("at_site"))
            current = to_float(data.get("current"))
            power = to_float(data.get("power"))

            # Normalize units from HA unit_of_measurement to what the
            # Venus dbus wiki expects. HA reports power in kW; /Ac/Power is
            # W. Odometer/range-to-go may be miles; wiki expects km.
            power = self._normalize_unit(
                power,
                self.power_entity,
                {"kw": 1000.0},
                {"kw", "w", "watt"},
            )
            odometer = self._normalize_unit(
                odometer,
                self.odometer_entity,
                {"mi": 1.609344, "mile": 1.609344, "miles": 1.609344},
                {"mi", "mile", "miles", "km", "kilometer", "kilometre", "kilo"},
            )
            range_to_go = self._normalize_unit(
                range_to_go,
                self.range_to_go_entity,
                {"mi": 1.609344, "mile": 1.609344, "miles": 1.609344},
                {"mi", "mile", "miles", "km", "kilometer", "kilometre", "kilo"},
            )

            result.update(
                soc=soc,
                target_soc=target_soc,
                vin=vin,
                battery_capacity=battery_capacity,
                charging_state=charging_state,
                odometer=odometer,
                range_to_go=range_to_go,
                latitude=latitude,
                longitude=longitude,
                at_site=at_site,
                current=current,
                power=power,
                ok=soc is not None,  # Consider OK if we got at least SOC
            )
            self.last_known = {
                k: result[k]
                for k in (
                    "soc",
                    "target_soc",
                    "vin",
                    "battery_capacity",
                    "charging_state",
                    "odometer",
                    "range_to_go",
                    "latitude",
                    "longitude",
                    "at_site",
                    "current",
                    "power",
                )
            }
            self.breaker.record_success()
        except requests.exceptions.Timeout as exc:
            self.breaker.record_failure()
            self._log_error_throttled(f"HA timeout: {exc}")
        except requests.exceptions.RequestException as exc:
            self.breaker.record_failure()
            self._log_error_throttled(f"HA connection error: {exc}")
        except HomeAssistantError as exc:
            self.breaker.record_failure()
            self._log_error_throttled(str(exc))
        except ValueError as exc:
            self.breaker.record_failure()
            self._log_error_throttled(f"HA template returned invalid JSON: {exc}")
        return result
