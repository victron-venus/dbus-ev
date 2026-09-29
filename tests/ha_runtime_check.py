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
from homeassistant.components.sensor.recorder import _update_issues
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant

VIN = "WDD00000000000001"


def check_consumption_missing_data(hass, coordinator):
    """A missing consumption reading must never become a unitless numeric zero."""
    key = "electricconsumptionstart"
    reading = {
        "double_value": 24.408,
        "display_value": "2.5",
        "status": "VALID",
        "electricity_consumption_unit": "M_PER_KWH",
    }

    def receive(attribute):
        attributes = {"soc": {"int_value": "72", "status": "VALID"}}
        if attribute is not None:
            attributes[key] = attribute
        payload = {
            "schema": 1,
            "vin": VIN,
            "received_at": time.time(),
            "attributes": attributes,
        }
        coordinator._message(SimpleNamespace(payload=json.dumps(payload)))

    receive(reading)
    sensor = _create_sensor_if_eligible(
        key, SENSORS[key], coordinator.client.cars[VIN], coordinator
    )
    assert sensor is not None
    assert sensor.unique_id == VIN.lower() + "_electricconsumptionstart"
    sensor.entity_id = "sensor.test_electric_consumption_start"
    metadata = {
        sensor.entity_id: (
            1,
            {"unit_of_measurement": "mi/kWh", "unit_class": "energy_distance", "mean_type": None},
        )
    }

    def published():
        # Read the real entity projection without registering a live MQTT platform.
        sensor._state = sensor._get_car_value(
            sensor._feature_name, sensor._object_name, sensor._attrib_name, None
        )
        attributes = sensor.extra_state_attributes | {"state_class": sensor.state_class}
        if (unit := sensor.unit_of_measurement) is not None:
            attributes["unit_of_measurement"] = unit
        hass.states.async_set(sensor.entity_id, sensor.native_value, attributes)
        state = hass.states.get(sensor.entity_id)
        issues = []
        _update_issues(lambda *issue: issues.append(issue), [state], metadata, {})
        assert not issues, issues
        return state

    with patch("custom_components.mbapi2020.coordinator.mqtt.is_connected", return_value=True):
        coordinator._availability(SimpleNamespace(payload="online"))
        assert published().state == "2.5"
        assert published().attributes["unit_of_measurement"] == "mi/kWh"
        for invalid in (
            None,
            {"status": 4},
            {"status": "4"},
            {"status": 3},
            {"status": "NOT_RECEIVED"},
        ):
            receive(invalid)
            assert published().state == STATE_UNKNOWN
            receive(reading)
            state = published()
            assert state.state == "2.5"
            assert state.attributes["unit_of_measurement"] == "mi/kWh"
        # A real zero remains numeric and keeps the unit provided by the source.
        receive(dict(reading, double_value=0, display_value="0"))
        state = published()
        assert state.state == "0"
        assert state.attributes["unit_of_measurement"] == "mi/kWh"
        # The source still chooses the display value and unit; no fixed-unit override.
        receive(dict(reading, display_value="24.4", electricity_consumption_unit="KWH_PER_100KM"))
        state = published()
        assert state.state == "24.4"
        assert state.attributes["unit_of_measurement"] == "kWh/100km"


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
    check_consumption_missing_data(hass, coordinator)
    coordinator.stop()
    print(
        "HA runtime checks passed: sensor IDs, values, read-only covers, availability, "
        "expiry and missing-consumption recovery without fabricated statistics"
    )


asyncio.run(main())
