# Paho is optional for the HA-only backend.
# pylint: disable=import-outside-toplevel
"""One Cerbo MQTT session for optional HA telemetry publication and local metering."""

import json
import logging
import math
import threading
import time

logger = logging.getLogger(__name__)


class CerboMqtt:
    """One local MQTT connection for telemetry publication and meter consumption."""

    def __init__(
        self,
        *,
        host,
        port,
        portal,
        publish_ha=False,
        meter_instance=None,
        username="",
        password="",
        meter_ttl=15,
        client=None,
        source="mercedes",
        vehicle_id="vehicle",
    ):
        if not portal or any(char in portal for char in "/+#"):
            raise ValueError("CERBO_PORTAL_ID must be configured")
        if client is None:
            import paho.mqtt.client as mqtt

            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dbus-ev")
        self.client = client
        self.source = source
        if source != "mercedes" and (
            not vehicle_id or not all(c.isascii() and (c.isalnum() or c == "_") for c in vehicle_id)
        ):
            raise ValueError("BUS_SUFFIX must contain only ASCII letters, numbers and underscores")
        self.portal, self.publish_ha = portal, publish_ha
        self.prefix = f"mercedes/{portal}" if source == "mercedes" else f"ev/{portal}/{vehicle_id}"
        self.meter_prefix = f"N/{portal}/acload/{meter_instance}"
        self.meter_instance, self.meter_ttl = meter_instance, meter_ttl
        self._lock = threading.Lock()
        self._meter = {}
        self._connected = False
        self._published_revision = None
        self._last_keepalive = None
        self._availability = None
        self._started = False
        if username:
            client.username_pw_set(username, password)
        if publish_ha:
            client.will_set(self.prefix + "/availability", "offline", qos=1, retain=True)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=5, max_delay=120)
        self.host, self.port = host, port

    def start(self):
        self.client.connect_async(self.host, self.port, keepalive=60)
        self.client.loop_start()
        self._started = True

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            return
        with self._lock:
            self._connected = True
            self._meter.clear()
            self._published_revision = None
            self._availability = None
            self._last_keepalive = None
        if self.meter_instance is not None:
            client.subscribe(self.meter_prefix + "/#", qos=1)

    def _on_disconnect(self, *_args):
        with self._lock:
            self._connected = False
            self._meter.clear()

    def _on_message(self, client, userdata, message):
        if not message.topic.startswith(self.meter_prefix + "/") or message.retain:
            return
        key = message.topic[len(self.meter_prefix) :]
        try:
            value = json.loads(message.payload)["value"]
            value = float(value) if value is not None else None
            if value is not None and not math.isfinite(value):
                value = None
        except (TypeError, ValueError, KeyError):
            value = None
        with self._lock:
            self._meter[key] = (value, time.monotonic())

    def meter(self):
        now = time.monotonic()
        with self._lock:
            if not self._connected:
                return {}
            return {
                key: value
                for key, (value, at) in self._meter.items()
                if 0 <= now - at < self.meter_ttl
            }

    def tick(self, snapshot):
        now = time.monotonic()
        with self._lock:
            connected = self._connected
        if not connected:
            return
        if self.meter_instance is not None and (
            self._last_keepalive is None or now - self._last_keepalive >= 10
        ):
            self.client.publish(
                f"R/{self.portal}/keepalive", json.dumps([f"acload/{self.meter_instance}/#"])
            )
            self._last_keepalive = now
        if not self.publish_ha:
            return
        if self.source != "mercedes":
            self._publish_vehicle(snapshot)
            return
        payload = snapshot.get("mercedes_payload")
        available = bool(snapshot.get("ok") and payload)
        if available:
            revision = (payload["received_at"], payload["revision"])
            if revision != self._published_revision:
                result = self.client.publish(
                    f"{self.prefix}/{payload['vin']}/state",
                    json.dumps(payload, allow_nan=False, separators=(",", ":")),
                    qos=1,
                    retain=True,
                )
                if result.rc == 0:
                    self._published_revision = revision
        status = "online" if available else "offline"
        if status != self._availability:
            result = self.client.publish(self.prefix + "/availability", status, qos=1, retain=True)
            if result.rc == 0:
                self._availability = status

    def _publish_vehicle(self, snapshot):
        # Raw telemetry only: never create Home Assistant entities automatically.
        from dbus_ev.vehicle import MQTT_FIELDS  # pylint: disable=import-outside-toplevel

        available = bool(snapshot.get("ok") and snapshot.get("sampled_at") is not None)
        if available and snapshot["sampled_at"] != self._published_revision:
            payload = {key: snapshot.get(key) for key in MQTT_FIELDS}
            payload.update(
                schema=1, sampled_at=snapshot["sampled_at"], source=snapshot.get("source")
            )
            result = self.client.publish(
                self.prefix + "/state", json.dumps(payload, allow_nan=False), qos=1, retain=True
            )
            if result.rc == 0:
                self._published_revision = snapshot["sampled_at"]
        status = "online" if available else "offline"
        if status != self._availability:
            result = self.client.publish(self.prefix + "/availability", status, qos=1, retain=True)
            if result.rc == 0:
                self._availability = status

    def close(self):
        if not self._started:
            return
        if self.publish_ha and self._connected:
            info = self.client.publish(self.prefix + "/availability", "offline", qos=1, retain=True)
            try:
                info.wait_for_publish(timeout=2)
            except RuntimeError:
                pass
        self.client.disconnect()
        self.client.loop_stop()
