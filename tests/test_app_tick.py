"""Integration-ish tests for App.tick wiring with fake client/services."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

from dbus_ev.main import VEHICLE_PROPS, App, serve


class FakeClient:
    """Fake HA client that records calls and returns a canned snapshot."""

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def poll(self):
        return self.snapshot

    def call_service(self, domain, action, entity_id):
        self.calls.append((domain, action, entity_id))
        return True


class FakeServices:
    """Minimal services stand-in for App.tick."""

    def __init__(self, snapshot):
        self.items = {}
        for path in VEHICLE_PROPS:
            self.items[path] = snapshot.get(path)

    def set_connected(self, connected):
        pass

    def update_soc(self, soc):
        self.items["/Soc"] = soc

    def update_target_soc(self, target_soc):
        self.items["/TargetSoc"] = target_soc

    def update_vin(self, vin):
        self.items["/VIN"] = vin

    def update_battery_capacity(self, capacity):
        self.items["/BatteryCapacity"] = capacity

    def update_charging_state(self, state):
        self.items["/ChargingState"] = state

    def update_odometer(self, odometer):
        self.items["/Odometer"] = odometer

    def update_range_to_go(self, range_):
        self.items["/RangeToGo"] = range_

    def update_latitude(self, latitude):
        self.items["/Position/Latitude"] = latitude

    def update_longitude(self, longitude):
        self.items["/Position/Longitude"] = longitude

    def update_at_site(self, at_site):
        self.items["/AtSite"] = at_site

    def update_ac_power(self, power):
        self.items["/Ac/Power"] = power

    def update_current(self, current):
        self.items["/Current"] = current


BASE = {"soc": 50.0, "ok": True}


def build_app(snapshot):
    client = FakeClient(snapshot)
    services = FakeServices(snapshot)
    app = App(client, services)
    app.services = services
    app.client = client
    return app


def test_tick_publishes_soc(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    app = build_app(dict(BASE))
    app.tick()
    assert app.services.items["/Soc"] == 50.0
    assert app.client.calls == []  # nothing to command


def test_tick_updates_all_fields(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    snap = {
        "ok": True,
        "soc": 75.0,
        "target_soc": 80.0,
        "vin": "ABC123",
        "battery_capacity": 80.0,
        "charging_state": "charging",
        "odometer": 15000.0,
        "range_to_go": 200.0,
        "latitude": 37.77,
        "longitude": -122.4,
        "at_site": True,
    }
    app = build_app(snap)
    app.tick()
    assert app.services.items["/Soc"] == 75.0
    assert app.services.items["/TargetSoc"] == 80.0
    assert app.services.items["/VIN"] == "ABC123"
    assert app.services.items["/BatteryCapacity"] == 80.0
    assert app.services.items["/ChargingState"] == "charging"
    assert app.services.items["/Odometer"] == 15000.0
    assert app.services.items["/RangeToGo"] == 200.0
    assert app.services.items["/Position/Latitude"] == 37.77
    assert app.services.items["/Position/Longitude"] == -122.4
    assert app.services.items["/AtSite"] is True


def test_tick_stale_sets_connected_false(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    snap = {"ok": False, "soc": None}
    app = build_app(snap)
    app.tick()
    # ok=False means HA unreachable; connected should be False
    assert app.services.items["/Soc"] is None


def test_tick_no_control_when_disabled(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    snap = dict(BASE, soc=10.0)
    app = build_app(snap)
    app.tick()
    assert app.client.calls == []


def test_tick_computes_remaining_from_raw_height(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    app = build_app(dict(BASE))
    app.tick()


def test_tick_remaining_falls_back_to_capacity_derivation(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    app = build_app(dict(BASE))
    app.tick()


def test_tick_publishes_static_battery_capacity(monkeypatch):
    """Static literals must remain numeric for VRM configuration rounding."""
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr("dbus_ev.main.config.HA_BATTERY_CAPACITY_ENTITY", "118")
    monkeypatch.setattr("dbus_ev.main.config.BATTERY_CAPACITY_KWH", None)
    snap = dict(BASE, battery_capacity=None)
    app = build_app(snap)
    app.tick()
    assert app.services.items["/BatteryCapacity"] == 118.0


def test_tick_stale_publishes_invalid_level(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    snap = {"soc": None, "ok": False}
    app = build_app(snap)
    app.tick()
    assert app.services.items.get("/Soc") is None


def test_tick_decimal_battery_capacity_literal(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr("dbus_ev.main.config.HA_BATTERY_CAPACITY_ENTITY", "118.5")
    monkeypatch.setattr("dbus_ev.main.config.BATTERY_CAPACITY_KWH", 80.0)
    app = build_app(dict(BASE, battery_capacity=None))
    app.tick()
    assert app.services.items["/BatteryCapacity"] == 118.5


def test_tick_capacity_falls_back_without_entity(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr("dbus_ev.main.config.HA_BATTERY_CAPACITY_ENTITY", "")
    monkeypatch.setattr("dbus_ev.main.config.BATTERY_CAPACITY_KWH", 80.0)
    app = build_app(dict(BASE, battery_capacity=None))
    app.tick()
    assert app.services.items["/BatteryCapacity"] == 80.0


def test_cached_reader_keeps_outputs_fresh_without_duplicate_work(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr("dbus_ev.main._now", lambda: now[0])
    heartbeat = MagicMock()
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", heartbeat)
    monkeypatch.setattr("dbus_ev.main.config.DATA_SOURCE", "mercedes")
    monkeypatch.setattr("dbus_ev.main.config.MERCEDES_STALE_TIMEOUT", 15)
    snapshot = {"ok": True, "soc": 42, "_source_sample_started_at": 1000.0}
    reader = MagicMock(return_value=snapshot)
    client, services, mqtt, charger = (MagicMock() for _ in range(4))
    app = App(client, services, mqtt=mqtt, charger=charger, snapshot_reader=reader)

    assert app.tick() is True
    client.poll.assert_not_called()
    services.set_connected.assert_called_once_with(True)
    mqtt.tick.assert_called_once()
    charger.update.assert_called_once()
    heartbeat.assert_called_once()

    # The cache reader must not renew the source time; expiry and meter updates
    # still run even when the vehicle has sent no new data.
    now[0] += 15
    assert app.tick() is True
    services.set_connected.assert_called_with(False)
    assert mqtt.tick.call_args.args[0]["ok"] is False
    assert charger.update.call_args.args[0]["ok"] is False
    assert mqtt.meter.call_count == 2
    assert snapshot["ok"] is True


def test_serve_uses_cache_reader_without_poll_thread(monkeypatch):
    glib = MagicMock()
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(GLib=glib))
    monkeypatch.setattr("dbus_ev.main.signal.signal", lambda *_: None)
    worker_factory = MagicMock()
    monkeypatch.setattr("dbus_ev.main.PollWorker", worker_factory)
    client, services = MagicMock(), MagicMock()
    app = App(client, services, snapshot_reader=client.cached_snapshot)
    serve(app)
    worker_factory.assert_not_called()
    glib.timeout_add.assert_called_once_with(app.loop_interval_ms, app.tick)
    assert app.worker is None
    app.shutdown()
    client.close.assert_called_once()


def test_serve_keeps_network_polls_on_worker(monkeypatch):
    glib = MagicMock()
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(GLib=glib))
    monkeypatch.setattr("dbus_ev.main.signal.signal", lambda *_: None)
    worker_factory = MagicMock()
    monkeypatch.setattr("dbus_ev.main.PollWorker", worker_factory)
    app = App(MagicMock(), MagicMock())
    serve(app)
    worker_factory.assert_called_once_with(app.client, glib.idle_add)
    app.shutdown()
    worker_factory.return_value.stop.assert_called_once()
