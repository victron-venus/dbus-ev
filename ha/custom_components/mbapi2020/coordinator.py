# The extracted upstream decoder exposes _build_car as its ingestion method.
# pylint: disable=protected-access
"""MQTT snapshots and availability, including retained-message expiry."""

import asyncio
import json
import logging
import math
import time
from datetime import timedelta

from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .car import CarAttribute, RcpOptions
from .decoder import Decoder

LOGGER = logging.getLogger(__name__)


class MBAPI2020DataUpdateCoordinator(DataUpdateCoordinator):
    """Receive Cerbo telemetry and expire stale snapshots without cloud access."""

    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name="Mercedes via Cerbo MQTT", config_entry=entry)
        self.client = Decoder()
        self.vin = entry.data["vin"].upper()
        topic_prefix = entry.data.get("topic_prefix", "").strip("/")
        self.prefix = (
            topic_prefix + "/" if topic_prefix else ""
        ) + f"mercedes/{entry.data['portal_id']}"
        self.max_age = float(entry.data.get("stale_timeout", 300))
        self.received_at = 0
        self.online = False
        self._ready = asyncio.Event()
        self._unsubs = []
        self.discovery_callbacks = []
        self._discovery_pending = False

    @property
    def available(self):
        age = time.time() - self.received_at
        return bool(self.online and 0 <= age < self.max_age and mqtt.is_connected(self.hass))

    async def async_start(self):
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass,
                f"{self.prefix}/{self.vin}/state",
                self._message,
                qos=1,
            )
        )
        self._unsubs.append(
            await mqtt.async_subscribe(
                self.hass,
                f"{self.prefix}/availability",
                self._availability,
                qos=1,
            )
        )
        self._unsubs.append(
            async_track_time_interval(
                self.hass,
                self._expire,
                timedelta(seconds=10),
            )
        )
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=25)
        except TimeoutError as exc:
            raise ConfigEntryNotReady("Waiting for Mercedes telemetry from Cerbo MQTT") from exc

    @callback
    def _message(self, message):
        try:
            payload = json.loads(message.payload)
            if not isinstance(payload, dict):
                return
            if payload.get("schema") != 1 or payload.get("vin") != self.vin:
                return
            received_at = float(payload["received_at"])
            if (
                not math.isfinite(received_at)
                or received_at < self.received_at
                or received_at > time.time() + 30
            ):
                return
            if not isinstance(payload.get("attributes"), dict):
                return
            if not all(isinstance(value, dict) for value in payload["attributes"].values()):
                return
            vehicle = payload.get("vehicle", {})
            if not isinstance(vehicle, dict) or not isinstance(
                vehicle.get("information", {}), dict
            ):
                return
            self.client._build_car(payload, update_mode=False)
            car = self.client.cars[self.vin]
            # Keep upstream IDs and presentation; no cloud capabilities lookup.
            car.features = {}
            car.licenseplate = (
                self.config_entry.data.get("vehicle_name") or vehicle.get("name") or self.vin
            )
            car.baumuster_description = vehicle.get("model", "Mercedes-Benz")
            car.vehicle_information = vehicle.get("information", {})
            car.is_owner = vehicle.get("is_owner", False)
            # Upstream exposes this diagnostic as False (RCP discovery is disabled).
            # Remote control is likewise not offered by this telemetry-only adapter.
            car.rcp_options = RcpOptions()
            car.rcp_options.rcp_supported = CarAttribute(False, "VALID", 0)
            car.last_message_received = int(received_at * 1000)
            self.received_at = received_at
            self.async_set_updated_data(payload)
            self._ready.set()
            if self.discovery_callbacks and not self._discovery_pending:
                self._discovery_pending = True
                self.hass.async_create_task(self._discover())
        except (ValueError, KeyError, TypeError, OverflowError):
            LOGGER.warning("Rejected malformed Mercedes MQTT snapshot")

    async def _discover(self):
        try:
            for discover in self.discovery_callbacks:
                await discover(self.client.cars[self.vin])
        finally:
            self._discovery_pending = False

    @callback
    def _availability(self, message):
        self.online = message.payload == "online"
        self.async_update_listeners()

    @callback
    def _expire(self, _now):
        self.async_update_listeners()

    def stop(self):
        for unsubscribe in self._unsubs:
            unsubscribe()
        self._unsubs.clear()
