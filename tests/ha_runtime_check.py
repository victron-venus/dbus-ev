# Exercise callback boundaries and failure states without a live cloud connection.
# pylint: disable=protected-access
"""Run with HA's installed Python and the staged ha/ directory on PYTHONPATH.

An isolated HomeAssistant object verifies the real entity/coordinator APIs without
starting HA, connecting a broker, or issuing any vehicle/device command.
"""

import asyncio
import json
import time
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from custom_components.mbapi2020.config_flow import valid_route
from custom_components.mbapi2020.const import SENSORS
from custom_components.mbapi2020.coordinator import MBAPI2020DataUpdateCoordinator
from custom_components.mbapi2020.cover import Window
from custom_components.mbapi2020.sensor import _create_sensor_if_eligible
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

VIN = "WDD00000000000001"


async def main():
    hass = HomeAssistant("/tmp/mercedes-ha-isolated-test")
    entry = ConfigEntry(
        domain="mbapi2020",
        title="Test",
        source="user",
        version=1,
        minor_version=1,
        unique_id="test",
        data={"transport": "cerbo_mqtt", "vin": VIN, "portal_id": "testportal"},
        options={"cap_check_disabled": True},
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    coordinator = MBAPI2020DataUpdateCoordinator(hass, entry)
    assert coordinator.max_age == 900
    assert valid_route({"vin": VIN, "portal_id": "testportal", "topic_prefix": "victron/"})
    assert not valid_route({"vin": VIN, "portal_id": "testportal", "topic_prefix": "victron/#"})
    payload = {
        "schema": 1,
        "vin": VIN,
        "received_at": time.time(),
        "attributes": {
            "soc": {"int_value": "72", "status": "VALID"},
            "chargingstatus": {"int_value": "0", "status": "VALID"},
            "windowstatusfrontleft": {"int_value": "2", "status": "VALID"},
        },
    }
    coordinator._message(SimpleNamespace(payload=json.dumps(payload)))
    car = coordinator.client.cars[VIN]
    # Malformed optional metadata must neither escape the callback nor replace the state.
    previous = coordinator.received_at
    invalid = dict(payload, received_at=time.time(), vehicle=[])
    coordinator._message(SimpleNamespace(payload=json.dumps(invalid)))
    assert coordinator.received_at == previous
    sensor = _create_sensor_if_eligible("soc", SENSORS["soc"], car, coordinator)
    assert sensor is not None
    # HA calls CoordinatorEntity.async_update before adding a restored entity.
    # This must succeed without cloud I/O or renewing the snapshot acquisition.
    cached_data, acquired_at = coordinator.data, coordinator.received_at
    await sensor.async_update()
    assert coordinator.data is cached_data
    assert coordinator.received_at == acquired_at
    sensor._state = sensor._get_car_value(
        sensor._feature_name, sensor._object_name, sensor._attrib_name, None
    )
    assert float(sensor.native_value) == 72
    assert sensor.unique_id == VIN.lower() + "_soc"
    window = Window(coordinator, "window_front_left", "windowstatusfrontleft")
    assert window.is_closed is True
    assert window.supported_features == 0
    payload["data_mode"] = "pull"
    payload["received_at"] = time.time()
    coordinator._message(SimpleNamespace(payload=json.dumps(payload)))
    assert coordinator.client.cars[VIN].data_collection_mode.value == "pull"
    with patch("custom_components.mbapi2020.coordinator.mqtt.is_connected", return_value=True):
        coordinator._availability(SimpleNamespace(payload="online"))
        assert coordinator.available
        coordinator.received_at = time.time() - 301
        assert coordinator.available
        coordinator.received_at = time.time() - 899
        assert coordinator.available
        coordinator.received_at = time.time() - 901
        assert not coordinator.available
        # Retained replay cannot turn an old snapshot into current data.
        payload["received_at"] = time.time() - 1000
        coordinator._message(SimpleNamespace(payload=json.dumps(payload)))
        assert not coordinator.available
        coordinator._availability(SimpleNamespace(payload="offline"))
        assert not coordinator.available
    coordinator.stop()
    print("HA runtime checks passed: sensor IDs, values, read-only covers, availability and expiry")


asyncio.run(main())
