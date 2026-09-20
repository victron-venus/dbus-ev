# The extracted upstream decoder exposes _build_car as its ingestion method.
# pylint: disable=protected-access
"""One async Mercedes connection, with a nonblocking snapshot for the GLib loop."""

import asyncio
import copy
import logging
import math
import threading
import time
import uuid

import aiohttp

from dbus_ev.ha_client import map_charging_state

from .oauth import MBAuthError, Oauth
from .protocol import Protocol, finite
from .store import TokenStore
from .vendor.app_version import AppVersionManager
from .vendor.decoder import Decoder
from .vendor.helper import UrlHelper

logger = logging.getLogger(__name__)


def vehicle_snapshot(payload, capacity=None):
    decoder = Decoder()
    decoder._build_car(payload, update_mode=False)
    car = decoder.cars[payload["vin"]]

    def value(group, field):
        attr = getattr(getattr(car, group, None), field, None)
        if attr is None or str(attr.retrievalstatus) != "VALID":
            return None
        return attr.value

    def distance(field):
        group = "odometer" if field == "odo" else "electric"
        number = finite(value(group, field))
        attr = getattr(getattr(car, group, None), field, None)
        if number is not None and str(getattr(attr, "unit", "")).upper() == "MILES":
            number *= 1.609344
        return number

    raw_status = value("electric", "chargingstatus")
    status = map_charging_state(str(raw_status)) if raw_status is not None else None
    power = finite(value("electric", "chargingPower"))
    if power is None and finite(raw_status) == 3:
        # Mercedes omits chargingPower when the cable is explicitly unplugged.
        # Charging power is then zero; other missing/invalid readings stay unknown.
        power = 0.0
    return {
        "soc": finite(value("electric", "soc")),
        "target_soc": finite(value("electric", "max_soc")),
        "vin": payload["vin"],
        "battery_capacity": capacity,
        "charging_state": status,
        "mercedes_charging_status": finite(raw_status),
        "odometer": distance("odo"),
        "range_to_go": distance("rangeelectric"),
        "latitude": finite(value("location", "positionLat")),
        "longitude": finite(value("location", "positionLong")),
        "at_site": None,
        "power": power * 1000 if power is not None else None,
        "current": None,
    }


class MercedesClient:
    """Maintain one OAuth/WebSocket session and a freshness-bound snapshot."""

    def __init__(
        self, *, vin, region, token_file, stale_timeout=300, capacity=None, home=(None, None, 150)
    ):
        if len(vin) != 17 or not vin.isascii() or not vin.isalnum():
            raise ValueError("MERCEDES_VIN must be a 17-character VIN")
        if not UrlHelper.Websocket_url(region):
            raise ValueError("Unsupported MERCEDES_REGION")
        self.vin, self.region = vin.upper(), region
        self.store = TokenStore(token_file)
        self.stale_timeout, self.capacity = stale_timeout, capacity
        self.home = home
        self._lock = threading.Lock()
        self._snapshot = {"ok": False}
        self._payload = None
        self._received = None
        self._connected = False
        self._stop = threading.Event()
        self._loop = self._task = self._thread = None

    def start(self):
        if self._thread is not None:
            return
        self.store.acquire()
        self._thread = threading.Thread(target=self._run, name="mercedes", daemon=True)
        self._thread.start()

    def _run(self):
        try:
            asyncio.run(self._serve())
        except asyncio.CancelledError:
            pass
        finally:
            self.store.close()

    async def _serve(self):
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        retry = 15
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            versions = AppVersionManager(self.region)
            auth = Oauth(session, self.region, self.store, versions)
            while not self._stop.is_set():
                try:
                    await versions.async_refresh(session)
                    token = await auth.async_get_cached_token()
                    if not token:
                        raise MBAuthError("Authorization required")
                    metadata = await self._metadata(session, token, versions)
                    session_id = str(uuid.uuid4()).upper()
                    headers = versions.apply_websocket_headers(
                        {
                            "Authorization": token["access_token"],
                            "APP-SESSION-ID": session_id,
                            "X-SessionId": session_id,
                            "X-TrackingId": str(uuid.uuid4()).upper(),
                            "OUTPUT-FORMAT": "PROTO",
                            "ris-os-name": "ios",
                            "ris-os-version": "26.3",
                            "X-Locale": "en-US",
                        }
                    )
                    protocol = Protocol(self.vin)
                    async with session.ws_connect(
                        UrlHelper.Websocket_url(self.region),
                        headers=headers,
                        heartbeat=30,
                        max_msg_size=8 * 1024 * 1024,
                    ) as ws:
                        logger.info("Mercedes telemetry connected")
                        # A responsive socket can stop delivering vehicle data.
                        # Pongs and updates for another VIN must not extend this deadline.
                        async with asyncio.timeout(self.stale_timeout) as deadline:
                            async for message in ws:
                                if message.type != aiohttp.WSMsgType.BINARY:
                                    if message.type == aiohttp.WSMsgType.ERROR:
                                        break
                                    continue
                                ack, payload = protocol.decode(message.data)
                                if ack is not None:
                                    await ws.send_bytes(ack)
                                if payload is not None:
                                    payload["vehicle"] = metadata
                                    snapshot = vehicle_snapshot(payload, self.capacity)
                                    snapshot["at_site"] = at_site(snapshot, self.home)
                                    with self._lock:
                                        self._payload, self._snapshot = payload, snapshot
                                        self._received = time.monotonic()
                                        self._connected = True
                                    deadline.reschedule(self._loop.time() + self.stale_timeout)
                                    retry = 15
                except MBAuthError:
                    logger.error(
                        "Mercedes authorization required; run the standalone login command"
                    )
                    retry = max(retry, 300)
                except Exception as exc:  # noqa: BLE001 -- malformed cloud frames must reconnect
                    # Do not log tokens, raw frames, account data or HTTP response bodies.
                    logger.warning("Mercedes connection interrupted (%s)", type(exc).__name__)
                    if getattr(exc, "status", None) in (401, 403, 429):
                        retry = max(retry, 300)
                finally:
                    with self._lock:
                        self._connected = False
                await asyncio.sleep(retry)
                retry = min(retry * 2, 900)

    async def _metadata(self, session, token, versions):
        """Fetch display metadata with the same token, without copying account data."""
        headers = versions.apply_webapi_headers(
            {
                "Authorization": f"Bearer {token['access_token']}",
                "X-SessionId": str(uuid.uuid4()).upper(),
                "X-TrackingId": str(uuid.uuid4()).upper(),
                "ris-os-name": "ios",
                "ris-os-version": "26.3",
                "X-Locale": "en-US",
                "Content-Type": "application/json; charset=UTF-8",
            }
        )
        metadata = {}
        try:
            async with session.get(
                UrlHelper.Rest_url(self.region) + "/v2/vehicles", headers=headers
            ) as response:
                response.raise_for_status()
                body = await response.json()
            for vehicle in body.get("assignedVehicles", []):
                if (vehicle.get("vin") or vehicle.get("fin")) == self.vin:
                    metadata["name"] = vehicle.get("licensePlate") or self.vin
                    metadata["model"] = (
                        vehicle.get("salesRelatedInformation", {})
                        .get("baumuster", {})
                        .get("baumusterDescription", "Mercedes-Benz")
                    )
                    metadata["is_owner"] = bool(vehicle.get("isOwner"))
            async with session.get(
                f"{UrlHelper.Rest_url(self.region)}/v1/vehicle/{self.vin}/capabilities",
                headers=headers,
            ) as response:
                response.raise_for_status()
                capabilities = await response.json()
            info = capabilities.get("vehicle", {})
            metadata["information"] = {
                key: info[key]
                for key in (
                    "headUnitSoftwareVersion",
                    "headUnitType",
                    "starArchitecture",
                    "tcuType",
                )
                if key in info
            }
        except aiohttp.ClientResponseError as exc:
            if exc.status in (401, 403, 429):
                raise
            logger.warning("Mercedes display metadata unavailable; telemetry will still connect")
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            logger.warning("Mercedes display metadata unavailable; telemetry will still connect")
        return metadata

    def poll(self):
        with self._lock:
            result = dict(self._snapshot)
            fresh = (
                self._received is not None
                and 0 <= time.monotonic() - self._received < self.stale_timeout
            )
            result["ok"] = self._connected and fresh and result.get("soc") is not None
            result["_source_sample_started_at"] = self._received
            result["mercedes_payload"] = copy.deepcopy(self._payload)
            return result

    def close(self):
        self._stop.set()
        if self._loop and self._task and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._task.cancel)
        if self._thread:
            self._thread.join(timeout=3)


def at_site(snapshot, home):
    lat, lon, radius = home
    current_lat, current_lon = snapshot.get("latitude"), snapshot.get("longitude")
    if any(finite(v) is None for v in (lat, lon, radius, current_lat, current_lon)):
        return None
    lat1, lat2 = math.radians(float(lat)), math.radians(current_lat)
    dlat = lat2 - lat1
    dlon = math.radians(current_lon - float(lon))
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    distance = 6371000 * 2 * math.asin(min(1, math.sqrt(a)))
    return distance <= float(radius)
