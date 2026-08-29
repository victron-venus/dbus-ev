"""Integration-ish tests for App.tick wiring with fake client/services."""

from dbus_ev.main import App


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
        for path in (
            "/Soc",
            "/TargetSoc",
            "/VIN",
            "/BatteryCapacity",
            "/ChargingState",
            "/Odometer",
            "/RangeToGo",
            "/Position/Latitude",
            "/Position/Longitude",
            "/AtSite",
        ):
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


def test_tick_stale_publishes_invalid_level(monkeypatch):
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    snap = {"soc": None, "ok": False}
    app = build_app(snap)
    app.tick()
    assert app.services.items.get("/Soc") is None
