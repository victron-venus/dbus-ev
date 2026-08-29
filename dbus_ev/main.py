"""Entry point: HA <-> D-Bus EV bridge."""

import argparse
import logging
import os
import signal
import sys
import time

from dbus_ev import config
from dbus_ev.ha_client import HaClient
from dbus_ev.service import VEDBUS_AVAILABLE, EVEvices

logger = logging.getLogger("dbus-ev")


def _now() -> float:
    return time.monotonic()


def _write_heartbeat() -> None:
    try:
        os.makedirs(os.path.dirname(config.HEARTBEAT_FILE), exist_ok=True)
        with open(config.HEARTBEAT_FILE, "w") as f:
            f.write(str(int(time.time())))
    except OSError as exc:  # /run may be read-only off-device
        logger.debug("heartbeat write failed: %s", exc)


def _setup_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


class App:
    def __init__(self, client: HaClient, services: EVEvices) -> None:
        self.client = client
        self.services = services
        self.last_ok_time: float | None = None
        self.loop_interval_ms = max(250, int(config.POLL_INTERVAL * 1000))

    def shutdown(self) -> None:
        # No action needed for EV
        pass

    # --- main cycle ----------------------------------------------------------
    def tick(self) -> bool:
        snapshot = self.client.poll()
        now_ok = snapshot["ok"]
        if now_ok:
            self.last_ok_time = _now()
        ha_reachable = (
            self.last_ok_time is not None
            and (_now() - self.last_ok_time) < config.SENSOR_STALE_TIMEOUT
        )
        self.services.set_connected(ha_reachable)

        if now_ok:
            self.services.update_soc(snapshot.get("soc"))
            self.services.update_target_soc(snapshot.get("target_soc"))
            self.services.update_vin(snapshot.get("vin"))
            self.services.update_battery_capacity(snapshot.get("battery_capacity"))
            self.services.update_charging_state(snapshot.get("charging_state"))
            self.services.update_odometer(snapshot.get("odometer"))
            self.services.update_range_to_go(snapshot.get("range_to_go"))
            self.services.update_latitude(snapshot.get("latitude"))
            self.services.update_longitude(snapshot.get("longitude"))
            self.services.update_at_site(snapshot.get("at_site"))

        _write_heartbeat()
        return True


def build_app() -> App:
    client = HaClient(
        base_url=config.HA_URL,
        token=config.HA_TOKEN,
        soc_entity=config.HA_SOC_ENTITY,
        target_soc_entity=config.HA_TARGET_SOC_ENTITY,
        vin_entity=config.HA_VIN_ENTITY,
        battery_capacity_entity=config.HA_BATTERY_CAPACITY_ENTITY,
        charging_state_entity=config.HA_CHARGING_STATE_ENTITY,
        odometer_entity=config.HA_ODOMETER_ENTITY,
        range_to_go_entity=config.HA_RANGE_TO_GO_ENTITY,
        latitude_entity=config.HA_LATITUDE_ENTITY,
        longitude_entity=config.HA_LONGITUDE_ENTITY,
        at_site_entity=config.HA_AT_SITE_ENTITY,
        timeout=config.HA_TIMEOUT,
    )
    services = EVEvices(
        ev_instance=config.DEVICE_INSTANCE,
        version=config.SOFTWARE_VERSION,
        product_name=config.PRODUCT_NAME,
        product_id=config.PRODUCT_ID,
    )
    app = App(client, services)
    return app


def serve(app: App) -> None:
    from gi.repository import GLib  # provided by Venus OS python env

    GLib.timeout_add(app.loop_interval_ms, app.tick)
    mainloop = GLib.MainLoop()

    def _stop(*_args):
        logger.info("Shutting down")
        app.shutdown()
        mainloop.quit()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("dbus-ev %s started", config.SOFTWARE_VERSION)
    mainloop.run()


def main() -> int:
    parser = argparse.ArgumentParser(description="HA EV system -> Venus OS D-Bus bridge")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run one control cycle against a NullDbusService and exit",
    )
    args = parser.parse_args()
    _setup_logging(args.debug)

    if args.dry_run:
        app = build_app()
        app.tick()
        # Print the EV service properties
        for prop in [
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
        ]:
            value = app.services.ev.get(prop, None)
            print(prop, value)
        return 0

    if not VEDBUS_AVAILABLE:
        logger.error("vedbus/dbus not available - run on the Cerbo GX")
        return 1
    from dbus.mainloop.glib import DBusGMainLoop

    # Must run before any VeDbusService is created (services export onto the
    # default main loop).
    DBusGMainLoop(set_as_default=True)
    serve(build_app())
    return 0


if __name__ == "__main__":
    sys.exit(main())
