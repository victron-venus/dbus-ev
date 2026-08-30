"""D-Bus service registration for EV (Venus OS).

Registers one service under the standard EV bus name per the Venus dbus wiki:
  com.victronenergy.ev.<suffix>

Where ``<suffix>`` is a textual identifier (port, serial, or fixed token) —
D-Bus bus names forbid digits after the last dot, so the integer instance
goes ONLY in the `/DeviceInstance` property, not in the bus name. This
matches the Victron convention used by dbus-modbus-client
(`com.victronenergy.evcharger.ttyO1`, `com.victronenergy.vebus.ttyO1`).

Vehicle paths exposed: /Soc, /TargetSoc, /VIN, /BatteryCapacity, /ChargingState,
/Odometer, /RangeToGo, /Position/Latitude, /Position/Longitude, /AtSite.

Off-GX (tests / dev laptop) a NullDbusService stand-in is used so the module
imports cleanly without velib_python/dbus.
"""

import logging
import typing

logger = logging.getLogger(__name__)

VEDBUS_AVAILABLE = False
try:
    # Add the velib_python path if it exists (Venus OS)
    import sys

    sys.path.insert(0, "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python")
    import dbus
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
        return VeDbusService(service_name, bus=dbus.SystemBus(private=True), register=False)
    return NullDbusService(service_name)


def _identity_paths(
    svc, *, product_name: str, version: str, custom_name: str, instance: int, connection: str
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


# VRM/CCGX expects these integer values on /Status.
STATUS_DISCONNECTED = 0
STATUS_CONNECTED = 1
STATUS_CHARGING = 2
STATUS_CHARGED = 3
STATUS_WAITING_FOR_SUN = 4


# D-Bus paths exposed on the EV service. Single source of truth — avoid
# string duplication by referencing these constants in update_*() methods.
PATH_SOC = "/Soc"
PATH_TARGET_SOC = "/TargetSoc"
PATH_VIN = "/VIN"
PATH_BATTERY_CAPACITY = "/BatteryCapacity"
PATH_CHARGING_STATE = "/ChargingState"
PATH_ODOMETER = "/Odometer"
PATH_RANGE_TO_GO = "/RangeToGo"
PATH_LATITUDE = "/Position/Latitude"
PATH_LONGITUDE = "/Position/Longitude"
PATH_AT_SITE = "/AtSite"
PATH_AC_POWER = "/Ac/Power"
PATH_AC_L1_POWER = "/Ac/L1/Power"


class EVEvices:
    """Owns the EV D-Bus service and its writable paths."""

    # Vehicle properties exposed on the EV D-Bus service (single source of truth).
    VEHICLE_PROPS: typing.ClassVar[tuple[str, ...]] = (
        PATH_SOC,
        PATH_TARGET_SOC,
        PATH_VIN,
        PATH_BATTERY_CAPACITY,
        PATH_CHARGING_STATE,
        PATH_ODOMETER,
        PATH_RANGE_TO_GO,
        PATH_LATITUDE,
        PATH_LONGITUDE,
        PATH_AT_SITE,
        PATH_AC_POWER,  # vehicle-side AC power (W)
        PATH_AC_L1_POWER,  # single-phase assumption
    )

    def __init__(
        self,
        *,
        ev_instance: int,
        version: str,
        product_name: str,
        product_id: int,
        connection: str,
        bus_suffix: str = "ha",
    ) -> None:
        # D-Bus bus names forbid digits after the last dot. The integer
        # instance lives in /DeviceInstance; the bus suffix is textual —
        # matches Victron convention (ttyO1, ttyUSB0, ha, etc.).
        bus_name = f"com.victronenergy.ev.{bus_suffix}"
        self.ev = _make_service(bus_name)
        _identity_paths(
            self.ev,
            product_name=product_name,
            version=version,
            custom_name=product_name,
            instance=ev_instance,
            connection=connection,
        )
        # Override ProductId with the provided one
        self.ev["/ProductId"] = product_id

        # --- standard EV charger paths (required by VRM for the dashboard) ---
        self.ev.add_path("/Status", STATUS_DISCONNECTED)
        self.ev.add_path("/NrOfPhases", 1)
        self.ev.add_path("/Position", 0)  # 0 = AC Output (grid/inverter -> car)
        self.ev.add_path("/PositionIsAdjustable", 0)
        self.ev.add_path("/IsGenericEnergyMeter", 0)
        self.ev.add_path("/Mode", 0)  # 0=Manual, 1=Auto, 2=Scheduled
        self.ev.add_path("/StartStop", 0)  # 0=Disabled, 1=Enabled
        self.ev.add_path(PATH_AC_POWER, 0)  # W
        self.ev.add_path("/Ac/Energy/Forward", 0)  # kWh
        self.ev.add_path(PATH_AC_L1_POWER, 0)
        self.ev.add_path("/Ac/L2/Power", 0)
        self.ev.add_path("/Ac/L3/Power", 0)
        self.ev.add_path("/Ac/L1/Voltage", 0)
        self.ev.add_path("/Ac/L1/Current", 0)
        self.ev.add_path("/Current", 0)  # A
        self.ev.add_path("/SetCurrent", 0)  # A setpoint (read-only here)
        self.ev.add_path("/MaxCurrent", 16)  # A — VRM expects it present
        self.ev.add_path("/ChargingTime", 0)  # s — current session
        self.ev.add_path("/Session/Energy", 0)  # kWh — current session

        # --- vehicle-specific paths (per Venus dbus wiki for com.victronenergy.ev) ---
        self.ev.add_path(PATH_SOC, None)
        self.ev.add_path(PATH_TARGET_SOC, None)
        self.ev.add_path(PATH_VIN, None)
        self.ev.add_path(PATH_BATTERY_CAPACITY, None)
        self.ev.add_path(PATH_CHARGING_STATE, None)  # Venus wiki enum int
        self.ev.add_path(PATH_ODOMETER, None)
        self.ev.add_path(PATH_RANGE_TO_GO, None)
        self.ev.add_path(PATH_LATITUDE, None)
        self.ev.add_path(PATH_LONGITUDE, None)
        self.ev.add_path(PATH_AT_SITE, None)

        # Register after all mandatory paths are added.
        if VEDBUS_AVAILABLE:
            self.ev.register()

    def update_soc(self, soc: float | None) -> None:
        self.ev[PATH_SOC] = soc

    def update_target_soc(self, target_soc: float | None) -> None:
        self.ev[PATH_TARGET_SOC] = target_soc

    def update_vin(self, vin: str | None) -> None:
        self.ev[PATH_VIN] = vin

    def update_battery_capacity(self, capacity: float | None) -> None:
        self.ev[PATH_BATTERY_CAPACITY] = capacity

    def update_charging_state(self, state: int | None) -> None:
        """Set the Victron enum int.

        Wrap in dbus.Int32 so it's published as a D-Bus INT32 variant;
        the GUI maps the enum int to a localized label, but only when
        the variant type matches. Without the wrap, the int is published
        as a STRING variant and the GUI shows "Unknown".
        """
        if VEDBUS_AVAILABLE:
            self.ev[PATH_CHARGING_STATE] = None if state is None else dbus.Int32(int(state))
        else:
            self.ev[PATH_CHARGING_STATE] = state

    def update_odometer(self, odometer: float | None) -> None:
        self.ev[PATH_ODOMETER] = odometer

    def update_range_to_go(self, range_: float | None) -> None:
        self.ev[PATH_RANGE_TO_GO] = range_

    def update_latitude(self, latitude: float | None) -> None:
        self.ev[PATH_LATITUDE] = latitude

    def update_longitude(self, longitude: float | None) -> None:
        self.ev[PATH_LONGITUDE] = longitude

    def update_at_site(self, at_site: bool | None) -> None:
        self.ev[PATH_AT_SITE] = at_site

    def update_ac_power(self, power_w: float | None) -> None:
        """Publish AC power (W) on /Ac/Power and /Ac/L1/Power."""
        if power_w is None:
            return
        self.ev[PATH_AC_POWER] = power_w
        self.ev[PATH_AC_L1_POWER] = power_w

    def update_current(self, _current_a: float | None) -> None:
        """No-op for EV service (no /Current path on the D-Bus wiki).
        Kept for compatibility with the HA client / app tick contract.
        """

    def set_connected(self, connected: bool) -> None:
        """Not used in EV service, but kept for compatibility with App."""
