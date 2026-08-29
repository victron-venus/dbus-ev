"""Tests for EVEvices D-Bus service registration and update methods."""

from dbus_ev.service import EVEvices, NullDbusService


def make_ev_services():
    return EVEvices(ev_instance=22, version="0.1.0", product_name="dbus-ev", product_id=0x1234)


def test_service_name():
    s = make_ev_services()
    assert s.ev.service_name == "com.victronenergy.evcharger.22"


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
    s.update_charging_state("charging")
    assert s.ev["/ChargingState"] == "charging"


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
