"""Local charger measurements remain independent of cloud availability."""

import pytest

from dbus_ev.charger import Charger


@pytest.fixture(name="charger")
def make_charger():
    return Charger(instance=40, version="test", bus_suffix="charger")


@pytest.mark.parametrize("power, expected_status", [(0, None), (40, None), (7200, 2)])
@pytest.mark.parametrize("at_site", [True, False, None])
def test_local_meter_survives_expired_vehicle_snapshot(charger, power, expected_status, at_site):
    # The last cloud snapshot may still contain old location and charging data.
    snapshot = {
        "ok": False,
        "charger_status": 3,
        "mercedes_charging_status": 13,
        "at_site": at_site,
        "power": 9000,
    }
    meter = {"/Ac/Power": power, "/Ac/L1/Power": power, "/Ac/Energy/Forward": 123}

    charger.update(snapshot, meter, require_meter=True)

    assert charger.service.svc["/Connected"] == 1
    assert charger.service.svc["/Ac/Power"] == power
    assert charger.service.svc["/Ac/L1/Power"] == power
    assert charger.service.svc["/Ac/Energy/Forward"] == 123
    assert charger.service.svc["/Status"] == expected_status
    assert charger.service.svc["/Session/Energy"] is None


def test_local_meter_is_available_before_first_vehicle_snapshot(charger):
    charger.update({"ok": False}, {"/Ac/Power": 0}, require_meter=True)

    assert charger.service.svc["/Connected"] == 1
    assert charger.service.svc["/Ac/Power"] == 0
    assert charger.service.svc["/Status"] is None


@pytest.mark.parametrize("meter", [{}, {"/Ac/Power": None}, {"/Ac/Power": 7200, "/Connected": 0}])
def test_expired_or_disconnected_meter_never_falls_back_to_cloud(charger, meter):
    snapshot = {"ok": True, "mercedes_charging_status": 13, "at_site": True, "power": 9000}
    charger.update(snapshot, {"/Ac/Power": 7200, "/Ac/L1/Power": 7200}, require_meter=True)

    charger.update(snapshot, meter, require_meter=True)

    assert charger.service.svc["/Connected"] == 0
    assert charger.service.svc["/Ac/Power"] is None
    assert charger.service.svc["/Ac/L1/Power"] is None


def test_cloud_only_charger_still_expires(charger):
    snapshot = {"ok": True, "mercedes_charging_status": 13, "at_site": True, "power": 9000}
    charger.update(snapshot)
    assert charger.service.svc["/Connected"] == 1
    assert charger.service.svc["/Ac/Power"] == 9000

    charger.update(dict(snapshot, ok=False), {"/Ac/Power": 7200})

    assert charger.service.svc["/Connected"] == 0
    assert charger.service.svc["/Ac/Power"] is None


def test_projection_registers_no_writable_charger_controls(monkeypatch):
    from dbus_ev import charger_service

    registered = {}

    class CapturingService(charger_service.NullDbusService):
        def add_path(self, path, value, *args, **kwargs):
            registered[path] = kwargs
            return super().add_path(path, value, *args, **kwargs)

    service = CapturingService("com.victronenergy.evcharger.test")
    monkeypatch.setattr(charger_service, "_make_service", lambda name: service)
    charger = Charger(instance=40, version="test", bus_suffix="test")
    controls = (
        "/Mode",
        "/StartStop",
        "/SetCurrent",
        "/AutoStart",
        "/EnableDisplay",
        "/MinCurrent",
        "/MaxCurrent",
    )
    assert all(path in registered for path in controls)
    assert not {path for path, options in registered.items() if options.get("writeable")}
    assert all(not registered[path].get("onchangecallback") for path in controls)
    # Read-only registration still permits the owning process to publish telemetry.
    charger.update({"ok": True, "charger_status": 2, "power": 7200})
    assert service["/Ac/Power"] == 7200
