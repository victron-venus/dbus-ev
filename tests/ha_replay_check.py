# Exercise callback boundaries and failure states without a live cloud connection.
# pylint: disable=protected-access
"""Replay a private, redacted upstream diagnostic snapshot in an isolated HA process.

Pass the prepared fixture path as argv[1]. Never commit account snapshots.
"""

import asyncio
import json
import sys
import time
from types import MappingProxyType, SimpleNamespace

from custom_components.mbapi2020.binary_sensor import _create_binary_sensor_if_eligible
from custom_components.mbapi2020.const import SENSORS, SENSORS_POLL, BinarySensors
from custom_components.mbapi2020.coordinator import MBAPI2020DataUpdateCoordinator
from custom_components.mbapi2020.sensor import _create_sensor_if_eligible
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

with open(sys.argv[1], encoding="utf-8") as fixture_file:
    fixture = json.load(fixture_file)


async def main():
    d = fixture
    h = HomeAssistant("/tmp/mercedes-replay-isolated")
    vin = "WDD00000000000001"
    e = ConfigEntry(
        domain="mbapi2020",
        title="Replay",
        source="user",
        version=1,
        minor_version=1,
        unique_id="replay",
        data={"transport": "cerbo_mqtt", "vin": vin, "portal_id": "testportal"},
        options={"cap_check_disabled": True},
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )
    c = MBAPI2020DataUpdateCoordinator(h, e)
    p = d["message"]
    p.update(schema=1, received_at=time.time())
    c._message(SimpleNamespace(payload=json.dumps(p)))
    car = c.client.cars[vin]
    matched = []
    missing = []
    errors = []
    for old in d["entities"]:
        domain, key = old["domain"], old["key"]
        if domain not in ("sensor", "binary_sensor"):
            continue
        configs = {**SENSORS, **SENSORS_POLL} if domain == "sensor" else BinarySensors
        internal = next((k for k in configs if slugify(k) == key), None)
        if internal is None:
            missing.append((domain, key, "definition"))
            continue
        cfg = configs[internal]
        ent = (
            _create_sensor_if_eligible(internal, cfg, car, c, internal in SENSORS_POLL, True)
            if domain == "sensor"
            else _create_binary_sensor_if_eligible(internal, cfg, car, c)
        )
        if ent is None:
            missing.append((domain, key, "eligibility"))
            continue
        try:
            ent._state = ent._get_car_value(
                ent._feature_name, ent._object_name, ent._attrib_name, None
            )
            _value = ent.native_value if domain == "sensor" else ent.is_on
            _attrs = ent.extra_state_attributes
        except Exception as ex:  # noqa: BLE001 -- report every replay mismatch
            errors.append((key, type(ex).__name__, str(ex)))
        else:
            assert ent.unique_id == vin.lower() + "_" + key
            matched.append((domain, key))
    print(json.dumps({"matched": len(matched), "missing": missing, "errors": errors}))
    assert not missing and not errors


asyncio.run(main())
