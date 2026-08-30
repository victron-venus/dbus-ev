"""D-Bus service registration for EV (Venus OS).

Registers one service under the standard EV charger bus name so VRM Portal
recognises it (bus-name pattern is what VRM uses to identify device classes):
  com.victronenergy.evcharger.<suffix>  - EV state from HA

Where ``<suffix>`` is a textual identifier (port, serial, or fixed token) —
D-Bus bus names forbid digits after the last dot, so the integer instance
goes ONLY in the `/DeviceInstance` property, not in the bus name. This
matches the Victron convention used by dbus-modbus-client
(`com.victronenergy.evcharger.ttyO1`, `com.victronenergy.vebus.ttyO1`).

Vehicle metrics (/Soc, /TargetSoc, /VIN, /Odometer, /RangeToGo, /Position/*,
/AtSite) are exposed alongside the standard EV charger paths (/Status,
/Ac/Power, /Current, /SetCurrent) so VRM renders the device in its
dashboard.

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

    def get(self, path, default=None):
        return self.items.get(path, default)

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


# --- EV charger status (int) — VRM/CCGX expects these integer values -----------
STATUS_DISCONNECTED = 0
STATUS_CONNECTED = 1
STATUS_CHARGING = 2
STATUS_CHARGED = 3
STATUS_WAITING_FOR_SUN = 4


# Map an HA `charging_status` string ("0".."N") to an int status code.
# Unknown / unavailable -> None (path left absent).
_CHARGING_STATUS_FROM_STRING = {
    "0": STATUS_DISCONNECTED,
    "1": STATUS_CONNECTED,
    "2": STATUS_CHARGING,
    "3": STATUS_CHARGED,
}


def _parse_charging_status(raw: object) -> int | None:
    """Coerce a free-form HA state (string/int) to a charger status int.

    Accepts numeric codes as strings ("0".."3") — the mbapi2020 integration
    exposes `charging_status` as a stringified integer. Anything else
    (including "unknown"/"unavailable"/None) returns None.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in ("none", "unknown", "unavailable"):
        return None
    return _CHARGING_STATUS_FROM_STRING.get(s)


class EVEvices:
    """Owns the EV D-Bus service and its writable paths."""

    def __init__(
        self,
        ev_instance: int,
        version: str,
        product_name: str,
        product_id: int,
        bus_suffix: str = "ha",
    ) -> None:
        # D-Bus bus names forbid digits after the last dot. The integer
        # instance lives in /DeviceInstance; the bus suffix is textual —
        # matches Victron convention (ttyO1, ttyUSB0, ha, etc.).
        bus_name = f"com.victronenergy.evcharger.{bus_suffix}"
        self.ev = _make_service(bus_name)
        _identity_paths(self.ev, product_name, version, product_name, ev_instance, "Home Assistant")
        # Override ProductId with the provided one
        self.ev["/ProductId"] = product_id

        # --- standard EV charger paths (required by VRM for the dashboard) ---
        # AC measurement (vehicle-side: what is flowing into the car). We
        # only have HA-derived state here, not live AC telemetry, so these
        # stay at 0 unless a power/current entity is wired up.
        self.ev.add_path("/Status", STATUS_DISCONNECTED)
        self.ev.add_path("/NrOfPhases", 1)
        self.ev.add_path("/Position", 0)  # 0 = AC Output (grid/inverter -> car)
        self.ev.add_path("/PositionIsAdjustable", 0)
        self.ev.add_path("/IsGenericEnergyMeter", 0)
        self.ev.add_path("/Mode", 0)  # 0=Manual, 1=Auto, 2=Scheduled
        self.ev.add_path("/StartStop", 0)  # 0=Disabled, 1=Enabled
        self.ev.add_path("/Ac/Power", 0)  # W
        self.ev.add_path("/Ac/Energy/Forward", 0)  # kWh
        self.ev.add_path("/Ac/L1/Power", 0)
        self.ev.add_path("/Ac/L2/Power", 0)
        self.ev.add_path("/Ac/L3/Power", 0)
        self.ev.add_path("/Ac/L1/Voltage", 0)
        self.ev.add_path("/Ac/L1/Current", 0)
        self.ev.add_path("/Current", 0)  # A
        self.ev.add_path("/SetCurrent", 0)  # A setpoint (read-only here)
        self.ev.add_path("/MaxCurrent", 16)  # A — VRM expects it present
        self.ev.add_path("/ChargingTime", 0)  # s — current session
        self.ev.add_path("/Session/Energy", 0)  # kWh — current session

        # --- vehicle-specific paths (not standard EV charger paths) ----------
        self.ev.add_path("/Soc", None)
        self.ev.add_path("/TargetSoc", None)
        self.ev.add_path("/VIN", None)
        self.ev.add_path("/BatteryCapacity", None)
        self.ev.add_path("/ChargingState", None)  # raw HA value (string)
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
        """Set both the raw HA string and the int /Status VRM expects."""
        self.ev["/ChargingState"] = state
        status = _parse_charging_status(state)
        if status is not None:
            self.ev["/Status"] = status

    def update_ac_power(self, power_w: float | None) -> None:
        if power_w is not None:
            self.ev["/Ac/Power"] = power_w
            self.ev["/Ac/L1/Power"] = power_w  # single-phase assumption

    def update_current(self, current_a: float | None) -> None:
        if current_a is not None:
            self.ev["/Current"] = current_a
            self.ev["/Ac/L1/Current"] = current_a

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
