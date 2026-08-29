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
TEMPLATE_BODY = """{{ {
  'soc': states('@SOC@') | string,
  'target_soc': states('@TARGET_SOC@') | string,
  'vin': states('@VIN@') | string,
  'battery_capacity': states('@BATTERY_CAPACITY@') | string,
  'charging_state': states('@CHARGING_STATE@') | string,
  'odometer': states('@ODOMETER@') | string,
  'range_to_go': states('@RANGE_TO_GO@') | string,
  'latitude': states('@LATITUDE@') | string,
  'longitude': states('@LONGITUDE@') | string,
  'at_site': states('@AT_SITE@') | string
} | to_json }}"""


class HomeAssistantError(Exception):
    """Base class for HA client errors."""


class HomeAssistantAPIError(HomeAssistantError):
    pass


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


def build_template(
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
) -> str:
    return (
        TEMPLATE_BODY.replace("@SOC@", soc_entity)
        .replace("@TARGET_SOC@", target_soc_entity)
        .replace("@VIN@", vin_entity)
        .replace("@BATTERY_CAPACITY@", battery_capacity_entity)
        .replace("@CHARGING_STATE@", charging_state_entity)
        .replace("@ODOMETER@", odometer_entity)
        .replace("@RANGE_TO_GO@", range_to_go_entity)
        .replace("@LATITUDE@", latitude_entity)
        .replace("@LONGITUDE@", longitude_entity)
        .replace("@AT_SITE@", at_site_entity)
    )


class HaClient:
    def __init__(
        self,
        base_url: str,
        token: str,
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
        timeout: float = 3.0,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
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
        }
        self._template = build_template(
            soc_entity,
            target_soc_entity,
            vin_entity,
            battery_capacity_entity,
            charging_state_entity,
            odometer_entity,
            range_to_go_entity,
            latitude_entity,
            longitude_entity,
            at_site_entity,
        )
        self._configured = all(
            (
                base_url,
                token,
                soc_entity,
                target_soc_entity,
                vin_entity,
                battery_capacity_entity,
                charging_state_entity,
                odometer_entity,
                range_to_go_entity,
                latitude_entity,
                longitude_entity,
                at_site_entity,
            )
        )
        self._session = requests.Session()
        if token:
            self._session.headers.update(
                {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            )
        self._last_error_log = 0.0

    def _log_error_throttled(self, msg: str) -> None:
        now = time.monotonic()
        if now - self._last_error_log >= 60.0:
            self._last_error_log = now
            logger.error(msg)

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
            self._log_error_throttled("HA client not configured (local_config.py missing?)")
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
            def to_float(s: str | None) -> float | None:
                if s is None:
                    return None
                s = s.strip()
                if s == "":
                    return None
                try:
                    return float(s)
                except ValueError:
                    return None

            soc = to_float(str(data.get("soc", "")).strip())
            target_soc = to_float(str(data.get("target_soc", "")).strip())
            vin = str(data.get("vin", "")).strip() or None
            battery_capacity = to_float(str(data.get("battery_capacity", "")).strip())
            charging_state = str(data.get("charging_state", "")).strip() or None
            odometer = to_float(str(data.get("odometer", "")).strip())
            range_to_go = to_float(str(data.get("range_to_go", "")).strip())
            latitude = to_float(str(data.get("latitude", "")).strip())
            longitude = to_float(str(data.get("longitude", "")).strip())
            at_site = state_is_on(data.get("at_site"))

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