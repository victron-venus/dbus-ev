"""D-Bus service registration for EV (Venus OS).

Registers one service:
  com.victronenergy.ev<N> - EV state from HA (no dot before instance: D-Bus
    well-known names don't allow digits after a dot)

Off-GX (tests / dev laptop) a NullDbusService stand-in is used so the module
imports cleanly without velib_python/dbus.
"""

import logging

logger = logging.getLogger(__name__)

VEDBUS_AVAILABLE = False
try:
    # Add the velib_python path if it exists (Venus OS)
    import sys

    sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
    import dbus  # noqa: F401
    from vedbus import VeDbusService

    VEDBUS_AVAILABLE = True
except ImportError:
    logger.info("vedbus/dbus unavailable - using NullDbusService (off-GX mode)")


class NullDbusService:
    """Dict-like stand-in for VeDbusService used off-device."""

    def __init__(self, service_name: str, **_kwargs) -> None:
        self.service_name = service_name
        self.items: dict[str, object] = {}
        self._onchange: dict[str, callable] = {}

    def add_path(self, path, value, description="", writeable=False, onchangecallback=None, **_kw):
        self.items[path] = value
        if onchangecallback:
            self._onchange[path] = onchangecallback

    def __setitem__(self, path, value):
        old = self.items.get(path)
        self.items[path] = value
        cb = self._onchange.get(path)
        if cb and old != value:
            cb(path, value)  # match vedbus (path, value) signature

    def __getitem__(self, path):
        return self.items[path]

    def __delitem__(self, path):
        del self.items[path]


def _make_service(service_name: str):
    if VEDBUS_AVAILABLE:
        # One private connection per service: VeDbusService exports at '/',
        # and a single connection can register that object path only once.
        import dbus

        return VeDbusService(service_name, bus=dbus.SystemBus(private=True), register=False)
    return NullDbusService(service_name)


def _identity_paths(
    svc, product_name: str, version: str, custom_name: str, instance: int, connection: str
):
    svc.add_path("/Mgmt/ProcessName", __file__)
    svc.add_path("/Mgmt/ProcessVersion", version)
    svc.add_path("/Mgmt/Connection", connection)
    svc.add_path("/DeviceInstance", instance)
    svc.add_path("/ProductName", product_name)
    svc.add_path("/ProductId", 0)  # placeholder, should be set from local_config.py
    svc.add_path("/FirmwareVersion", version)
    svc.add_path("/HardwareVersion", "n/a")
    svc.add_path("/Serial", f"dbev-{instance}")
    svc.add_path("/CustomName", custom_name)
    svc.add_path("/Connected", 1)


class EVEvices:
    """Owns the EV D-Bus service and its writable paths."""

    def __init__(
        self,
        ev_instance: int,
        version: str,
        product_name: str,
        product_id: int,
    ) -> None:
        bus_name = f"com.victronenergy.ev{ev_instance}"
        self.ev = _make_service(bus_name)
        _identity_paths(self.ev, product_name, version, product_name, ev_instance, "Home Assistant")
        # Override ProductId with the provided one
        self.ev["/ProductId"] = product_id

        # EV properties (read-only for now)
        self.ev.add_path("/Soc", None)
        self.ev.add_path("/TargetSoc", None)
        self.ev.add_path("/VIN", None)
        self.ev.add_path("/BatteryCapacity", None)
        self.ev.add_path("/ChargingState", None)
        self.ev.add_path("/Odometer", None)
        self.ev.add_path("/RangeToGo", None)
        self.ev.add_path("/Position/Latitude", None)
        self.ev.add_path("/Position/Longitude", None)
        self.ev.add_path("/AtSite", None)

        # Register after all mandatory paths are added.
        if VEDBUS_AVAILABLE:
            self.ev.register()

    def update_soc(self, soc: float | None) -> None:
        self.ev["/Soc"] = soc

    def update_target_soc(self, target_soc: float | None) -> None:
        self.ev["/TargetSoc"] = target_soc

    def update_vin(self, vin: str | None) -> None:
        self.ev["/VIN"] = vin

    def update_battery_capacity(self, capacity: float | None) -> None:
        self.ev["/BatteryCapacity"] = capacity

    def update_charging_state(self, state: str | None) -> None:
        self.ev["/ChargingState"] = state

    def update_odometer(self, odometer: float | None) -> None:
        self.ev["/Odometer"] = odometer

    def update_range_to_go(self, range_: float | None) -> None:
        self.ev["/RangeToGo"] = range_

    def update_latitude(self, latitude: float | None) -> None:
        self.ev["/Position/Latitude"] = latitude

    def update_longitude(self, longitude: float | None) -> None:
        self.ev["/Position/Longitude"] = longitude

    def update_at_site(self, at_site: bool | None) -> None:
        self.ev["/AtSite"] = at_site

    def set_connected(self, connected: bool) -> None:
        # Not used in EV service, but kept for compatibility with App
        pass
