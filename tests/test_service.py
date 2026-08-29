from dbus_pump.service import NullDbusService, WaterSystemServices


def build(**kw):
    kw.setdefault("on_pump_mode", lambda m: None)
    kw.setdefault("on_valve_mode", lambda m: None)
    return WaterSystemServices(
        tank_instance=21,
        pump_startstop_instance=1,
        valve_startstop_instance=2,
        version="0.1.0",
        **kw,
    )


def test_service_names():
    s = build()
    assert s.tank.service_name == "com.victronenergy.tank.ha_tank21"
    assert s.pump.service_name == "com.victronenergy.pump.startstop1"
    assert s.valve.service_name == "com.victronenergy.pump.startstop2"


def test_identity_paths_present():
    s = build()
    for svc in (s.tank, s.pump, s.valve):
        for p in (
            "/Mgmt/ProcessName",
            "/DeviceInstance",
            "/ProductId",
            "/ProductName",
            "/CustomName",
            "/Connected",
            "/Serial",
        ):
            assert p in svc.items, f"{svc.service_name} missing {p}"


def test_tank_fluid_type_fresh_water():
    s = build()
    assert s.tank.items["/FluidType"] == 1


def test_update_tank_level_and_remaining():
    s = build()
    s.capacity_m3 = 2.0
    s.update_tank_level(50.0)
    assert s.tank.items["/Level"] == 50.0
    assert s.tank.items["/Remaining"] == 1.0
    assert s.tank.items["/Status"] == 0
    s.update_tank_level(None)
    assert s.tank.items["/Level"] is None
    assert s.tank.items["/Status"] == 4


def test_capacity_from_constructor_published():
    s = build(capacity_m3=0.387)  # 387 L
    assert s.tank.items["/Capacity"] == 0.387


def test_remaining_fallback_capacity_times_level():
    s = build(capacity_m3=0.387)
    s.update_tank_level(100.0)
    assert s.tank.items["/Remaining"] == 0.387


def test_explicit_remaining_overrides_derivation():
    # level % is not volume-proportional when the sensor has a dead zone;
    # HA-computed liters must win.
    s = build(capacity_m3=0.387)
    s.update_tank_level(50.0, remaining_m3=0.15)
    assert s.tank.items["/Remaining"] == 0.15


def test_device_state_update():
    s = build()
    s.update_device_state("pump", True)
    assert s.pump.items["/State"] == 1
    s.update_device_state("valve", False)
    assert s.valve.items["/State"] == 0


def test_null_service_onchange_fires():
    seen = []
    svc = NullDbusService("test")
    svc.add_path("/Mode", 0, writeable=True, onchangecallback=lambda p, v: seen.append(v))
    svc["/Mode"] = 2
    assert seen == [2]
    svc["/Mode"] = 2  # no change -> no callback
    assert seen == [2]


def test_set_mode_quietly_does_not_fire_callback():
    seen = []
    s = build(on_valve_mode=lambda m: seen.append(m))
    s.set_mode_quietly("valve", 2)
    assert seen == []
    assert s.valve.items["/Mode"] == 2


def test_connected_propagates_to_all():
    s = build()
    s.set_connected(False)
    assert s.tank.items["/Connected"] == 0
    assert s.pump.items["/Connected"] == 0
    assert s.valve.items["/Connected"] == 0
    s.set_connected(True)
    assert s.valve.items["/Connected"] == 1
