"""Tests for EVEvices D-Bus service registration and update methods."""

import pytest

from dbus_ev.service import EVEvices, NullDbusService


def make_ev_services():
    return EVEvices(
        ev_instance=22,
        version="0.1.0",
        product_name="dbus-ev",
        product_id=0x1234,
        connection="evcharger:40",
        bus_suffix="ha",
    )


def test_service_name():
    s = make_ev_services()
    # D-Bus bus names forbid digits after the last dot; instance lives in
    # /DeviceInstance, suffix is textual.
    assert s.ev.service_name == "com.victronenergy.ev.ha"


def test_service_name_custom_suffix():
    s = EVEvices(
        ev_instance=22,
        version="0.1.0",
        product_name="dbus-ev",
        product_id=0x1234,
        connection="evcharger:40",
        bus_suffix="ttyO1",
    )
    assert s.ev.service_name == "com.victronenergy.ev.ttyO1"


def test_identity_paths_present():
    s = make_ev_services()
    for p in (
        "/Mgmt/ProcessName",
        "/Mgmt/ProcessVersion",
        "/Mgmt/Connection",
        "/DeviceInstance",
        "/ProductName",
        "/ProductId",
        "/FirmwareVersion",
        "/HardwareVersion",
        "/Serial",
        "/CustomName",
        "/Connected",
    ):
        assert p in s.ev.items, f"EV service missing {p}"
    assert s.ev.items["/DeviceInstance"] == 22
    assert s.ev.items["/ProductId"] == 0x1234


def test_vrm_evcharger_paths_present():
    """VRM Portal requires these standard EV charger paths to render the tile."""
    s = make_ev_services()
    for p in (
        "/Status",
        "/Mode",
        "/StartStop",
        "/Current",
        "/SetCurrent",
        "/MaxCurrent",
        "/Ac/Power",
        "/Ac/Energy/Forward",
        "/Ac/L1/Power",
        "/Ac/L2/Power",
        "/Ac/L3/Power",
        "/ChargingTime",
        "/Session/Energy",
        "/NrOfPhases",
        "/Position",
    ):
        assert p in s.ev.items, f"VRM evcharger path missing: {p}"


def test_vehicle_paths_present():
    """Per Venus dbus wiki for com.victronenergy.ev."""
    s = make_ev_services()
    for p in EVEvices.VEHICLE_PROPS:
        assert p in s.ev.items, f"Vehicle path missing: {p}"


def test_connection_evcharger_format():
    s = make_ev_services()
    assert s.ev.items["/Mgmt/Connection"] == "evcharger:40"


def test_update_soc_publishes():
    s = make_ev_services()
    s.update_soc(75.5)
    assert s.ev["/Soc"] == 75.5


def test_update_target_soc_publishes():
    s = make_ev_services()
    s.update_target_soc(80.0)
    assert s.ev["/TargetSoc"] == 80.0


def test_update_vin_publishes():
    s = make_ev_services()
    s.update_vin("WBA12345")
    assert s.ev["/VIN"] == "WBA12345"


def test_update_battery_capacity_publishes():
    s = make_ev_services()
    s.update_battery_capacity(80.0)
    assert s.ev["/BatteryCapacity"] == 80.0


def test_update_charging_state_publishes():
    s = make_ev_services()
    s.update_charging_state(3)  # charging
    assert s.ev["/ChargingState"] == 3


def test_update_odometer_publishes():
    s = make_ev_services()
    s.update_odometer(12345.0)
    assert s.ev["/Odometer"] == 12345.0


def test_update_range_to_go_publishes():
    s = make_ev_services()
    s.update_range_to_go(200.0)
    assert s.ev["/RangeToGo"] == 200.0


def test_update_latitude_publishes():
    s = make_ev_services()
    s.update_latitude(37.7749)
    assert s.ev["/Position/Latitude"] == 37.7749


def test_update_longitude_publishes():
    s = make_ev_services()
    s.update_longitude(-122.4194)
    assert s.ev["/Position/Longitude"] == -122.4194


def test_update_at_site_publishes():
    s = make_ev_services()
    s.update_at_site(True)
    assert s.ev["/AtSite"] is True


def test_set_connected_does_not_raise():
    s = make_ev_services()
    s.set_connected(True)
    s.set_connected(False)


def test_null_service_onchange_fires():
    seen = []
    svc = NullDbusService("test")
    svc.add_path("/Mode", 0, writeable=True, onchangecallback=lambda p, v: seen.append(v))
    svc["/Mode"] = 2
    assert seen == [2]
    svc["/Mode"] = 2  # no change -> no callback
    assert seen == [2]


def test_null_service_setitem_fires_callback_with_path():
    seen = []

    def cb(p, v):
        seen.append((p, v))

    svc = NullDbusService("test")
    svc.add_path("/Level", 0.0, onchangecallback=cb)
    svc["/Level"] = 50.0
    assert seen == [("/Level", 50.0)]


def test_null_service_add_path_without_callback():
    svc = NullDbusService("test")
    svc.add_path("/Foo", 1)
    svc["/Foo"] = 2
    assert svc["/Foo"] == 2


def test_null_service_getitem_raises_keyerror():
    svc = NullDbusService("test")
    try:
        svc["/Missing"]
    except KeyError:
        return
    raise AssertionError("Expected KeyError")


def test_null_service_delitem():
    svc = NullDbusService("test")
    svc.add_path("/Foo", 1)
    del svc["/Foo"]
    try:
        svc["/Foo"]
    except KeyError:
        return
    raise AssertionError("Expected KeyError after delete")


@pytest.mark.parametrize("value", ["118", "118.5", 118, 118.5])
def test_battery_capacity_is_numeric_for_vrmlogger(value):
    services = make_ev_services()
    services.update_battery_capacity(value)
    capacity = services.ev["/BatteryCapacity"]
    assert isinstance(capacity, float)
    # Same operation used by Venus OS vrmlogger for EV configuration.
    assert round(capacity, 1) == round(float(value), 1)


@pytest.mark.parametrize("value", [None, "unknown", "nan", "inf", -1])
def test_invalid_battery_capacity_is_unavailable(value):
    services = make_ev_services()
    services.update_battery_capacity(value)
    assert services.ev["/BatteryCapacity"] is None


def test_connected_reflects_ha_freshness():
    services = make_ev_services()
    assert services.ev["/Connected"] == 0
    services.set_connected(True)
    assert services.ev["/Connected"] == 1
    services.set_connected(False)
    assert services.ev["/Connected"] == 0


def test_unknown_power_invalidates_every_phase_used_by_dashboard_fallback():
    services = make_ev_services()
    paths = ["/Ac/Power", "/Ac/L1/Power", "/Ac/L2/Power", "/Ac/L3/Power"]
    for invalid in (None, float("nan"), float("inf"), 2**31):
        services.update_ac_power(7200)
        assert [services.ev[path] for path in paths] == [7200, 7200, 0, 0]
        services.update_ac_power(invalid)
        assert all(services.ev[path] is None for path in paths)
    services.update_ac_power(0)
    assert all(services.ev[path] == 0 for path in paths)
