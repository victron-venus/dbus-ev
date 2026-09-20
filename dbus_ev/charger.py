"""Charger projection owned by dbus-ev, without another Mercedes client."""

from .charger_service import EvChargerService


def charger_status(raw):
    if raw in (0, 5, 6, 9, 10, 11, 13, 14):
        return 2
    if raw == 1:
        return 3
    if raw == 3:
        return 0
    if raw in (2, 8, 12, 15):
        return 1
    return None


class Charger:
    """Project one shared vehicle snapshot and optional meter onto charger D-Bus."""

    def __init__(self, *, instance, version, bus_suffix, phases=1, name="EV Charger"):
        self.service = EvChargerService(
            instance,
            version,
            bus_suffix=bus_suffix,
            custom_name=name,
            product_name="dbus-ev",
            connection="Mercedes / local meter",
            register=False,
            on_mode=lambda *_: False,
            on_startstop=lambda *_: False,
            on_setcurrent=lambda *_: False,
        )
        self.phases = phases
        self.service.svc["/NrOfPhases"] = phases
        self.update({"ok": False})
        self.service.register()

    def update(self, snapshot, meter=None, require_meter=False):
        status = charger_status(snapshot.get("mercedes_charging_status"))
        if snapshot.get("at_site") is False:
            status = 0
        meter = meter or {}
        power = meter.get("/Ac/Power") if require_meter else snapshot.get("power")
        if require_meter and power is not None and power > 50:
            # The dedicated home circuit is stronger evidence than missing GPS.
            status = 2
        elif require_meter and snapshot.get("at_site") is None and status != 0:
            status = None
        usable = bool(snapshot.get("ok") and status is not None and power is not None)
        self.service.set_connected(usable)
        svc = self.service.svc
        svc["/Status"] = status if usable else 0
        svc["/Ac/Power"] = power if usable else None
        # Only a real lifetime meter can provide lifetime energy. Daily energy
        # and vehicle charge percentages are neither lifetime nor session energy.
        svc["/Ac/Energy/Forward"] = meter.get("/Ac/Energy/Forward") if usable else None
        svc["/Current"] = meter.get("/Ac/Current") if usable else None
        svc["/Ac/Frequency"] = meter.get("/Ac/Frequency") if usable else None
        for phase in (1, 2, 3):
            for field in ("Power", "Voltage", "Current", "PowerFactor"):
                path = f"/Ac/L{phase}/{field}"
                svc[path] = meter.get(path) if usable else None
        self.service.update_session(None, None)
