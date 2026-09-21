# Exercise callback boundaries and failure states without a live cloud connection.
# pylint: disable=protected-access
"""Protocol, units, shared snapshots, privacy and charger ownership regressions."""

import json
import os
import time
from unittest.mock import MagicMock

import pytest

from dbus_ev.cerbo_mqtt import CerboMqtt
from dbus_ev.charger import Charger, charger_status
from dbus_ev.mercedes.client import MercedesClient, at_site, vehicle_snapshot
from dbus_ev.mercedes.protocol import Protocol
from dbus_ev.mercedes.store import TokenStore
from dbus_ev.mercedes.vendor.proto import client_pb2, vehicle_events_pb2

VIN = "WDD00000000000001"


def attribute(value, timestamp=100, unit=None, status="VALID"):
    result = {
        "value": value,
        "timestamp_in_ms": timestamp * 1000,
        "timestamp": timestamp,
        "status": status,
    }
    if unit:
        result["distance_unit"] = unit
    return result


def payload(**attrs):
    return {
        "schema": 1,
        "vin": VIN,
        "received_at": time.time(),
        "revision": 1,
        "attributes": {key: attribute(value) for key, value in attrs.items()},
    }


def test_real_protobuf_frame_and_ack():
    message = vehicle_events_pb2.PushMessage()
    message.vepUpdates.sequence_number = 17
    car = message.vepUpdates.updates[VIN]
    car.vin, car.full_update = VIN, True
    car.attributes["soc"].int_value = 0
    ack, snap = Protocol(VIN).decode(message.SerializeToString())
    reply = client_pb2.ClientMessage.FromString(ack)
    assert reply.acknowledge_vep_updates_by_vin.sequence_number == 17
    assert vehicle_snapshot(snap)["soc"] == 0


def test_vsu_frame_preserves_proto_defaults_and_enum():
    message = vehicle_events_pb2.PushMessage()
    message.vehicle_status_updates.sequence_number = 21
    car = message.vehicle_status_updates.vehicle_status_updates[VIN]
    car.fin_or_vin, car.full_update = VIN, True
    car.soc.value = 0
    car.soc.metadata.timestamp.seconds = 100
    car.chargingstatus.value = 0
    car.chargingstatus.metadata.timestamp.seconds = 100
    car.charging_power.value = 7.2
    ack, snap = Protocol(VIN).decode(message.SerializeToString())
    reply = client_pb2.ClientMessage.FromString(ack)
    assert reply.acknowledge_vehicle_status_updates.sequence_number == 21
    result = vehicle_snapshot(snap)
    assert result["soc"] == 0
    assert result["charging_state"] == 3
    assert result["power"] == 7200


def test_partial_merge_order_and_vin_filter():
    protocol = Protocol(VIN)
    protocol.merge(payload(soc=70, chargingPower=7.2))
    update = payload(soc=71)
    update["attributes"]["soc"] = attribute(71, 101)
    snap = protocol.merge(update)
    assert snap["attributes"]["chargingPower"]["value"] == 7.2
    update["attributes"]["soc"] = attribute(9, 99)
    assert protocol.merge(update)["attributes"]["soc"]["value"] == 71
    message = vehicle_events_pb2.PushMessage()
    message.vepUpdates.updates["WDD99999999999999"].attributes["soc"].int_value = 20
    assert protocol.decode(message.SerializeToString())[1] is None


def test_full_update_clears_omitted_fields_and_invalid_readings():
    protocol = Protocol(VIN)
    protocol.merge(payload(soc=70, chargingPower=7.2))
    snap = protocol.merge(dict(payload(soc=0), full_update=True))
    assert "chargingPower" not in snap["attributes"]
    snap["attributes"]["soc"]["status"] = 3
    assert vehicle_snapshot(snap)["soc"] is None


def test_units_and_zero_values():
    snap = payload(soc=0, chargingstatus=0, chargingPower=0, odo=100, rangeelectric=50)
    snap["attributes"]["odo"]["distance_unit"] = "MILES"
    result = vehicle_snapshot(snap)
    assert result["soc"] == result["power"] == 0
    assert result["charging_state"] == 3
    assert result["odometer"] == pytest.approx(160.9344)
    assert result["range_to_go"] == 50
    snap["attributes"]["chargingPower"]["value"] = 7.2
    assert vehicle_snapshot(snap)["power"] == 7200


@pytest.mark.parametrize("charging_status", [None, 0, 1, 2, 3, 4, 7, 8, 13, 14, 16])
def test_unavailable_charging_power_is_zero_only_when_explicitly_unplugged(charging_status):
    snap = payload(soc=78)
    if charging_status is not None:
        snap["attributes"]["chargingstatus"] = attribute(charging_status)
    # Real Mercedes VEP representation when the cable is unplugged: no numeric
    # chargingPower and retrieval status 3, while chargingstatus itself is valid.
    snap["attributes"]["chargingPower"] = {"status": 3, "timestamp_in_ms": "100000"}
    assert vehicle_snapshot(snap)["power"] == (0 if charging_status == 3 else None)
    # The raw payload published to HA must retain the original API status.
    assert snap["attributes"]["chargingPower"] == {
        "status": 3,
        "timestamp_in_ms": "100000",
    }


def test_invalid_unplugged_status_does_not_imply_zero_power():
    snap = payload(soc=78, chargingstatus=3)
    snap["attributes"]["chargingstatus"]["status"] = "NOT_RECEIVED"
    assert vehicle_snapshot(snap)["power"] is None


def test_poll_does_not_renew_acquisition_age(tmp_path, monkeypatch):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    client._snapshot = {"soc": 50}
    client._received = 100
    client._connected = True
    monkeypatch.setattr("dbus_ev.mercedes.client.time.monotonic", lambda: 200)
    assert client.poll()["ok"] is True
    assert client.poll()["_source_sample_started_at"] == 100
    monkeypatch.setattr("dbus_ev.mercedes.client.time.monotonic", lambda: 1001)
    assert client.poll()["ok"] is False
    assert client._received == 100
    client._connected = False
    assert client.poll()["ok"] is False


def test_token_file_private_atomic_and_exclusive(tmp_path):
    path = tmp_path / "auth.json"
    first, second = TokenStore(path), TokenStore(path)
    first.acquire()
    with pytest.raises(RuntimeError, match="Another Mercedes client"):
        second.acquire()
    first.save({"token": {"refresh_token": "test-secret"}})
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert TokenStore(path).data["token"]["refresh_token"] == "test-secret"
    first.close()
    second.acquire()
    second.close()


def broker(publish=True, meter=85):
    wire = MagicMock()
    wire.publish.return_value.rc = 0
    mqtt = CerboMqtt(
        host="localhost",
        port=1883,
        portal="testportal",
        publish_ha=publish,
        meter_instance=meter,
        client=wire,
    )
    mqtt._on_connect(wire, None, None, 0)
    return mqtt, wire


def test_mqtt_publication_opt_in_and_no_poll_republication():
    mqtt, wire = broker(False, None)
    mqtt.tick({"ok": True, "mercedes_payload": payload(soc=50)})
    wire.publish.assert_not_called()
    wire.will_set.assert_not_called()
    mqtt, wire = broker(True, None)
    snap = {"ok": True, "mercedes_payload": payload(soc=50)}
    mqtt.tick(snap)
    count = wire.publish.call_count
    mqtt.tick(snap)
    assert wire.publish.call_count == count
    sent = wire.publish.call_args_list[0]
    assert sent.args[0] == f"mercedes/testportal/{VIN}/state"
    assert json.loads(sent.args[1])["attributes"]["soc"]["value"] == 50
    mqtt.tick(dict(snap, ok=False))
    assert wire.publish.call_args.args[1] == "offline"


def test_meter_requires_live_messages_and_independent_expiry(monkeypatch):
    mqtt, wire = broker()
    monkeypatch.setattr("dbus_ev.cerbo_mqtt.time.monotonic", lambda: 100)
    msg = MagicMock(topic="N/testportal/acload/85/Ac/Power", payload=b'{"value":0}', retain=True)
    mqtt._on_message(wire, None, msg)
    assert mqtt.meter() == {}
    msg.retain = False
    mqtt._on_message(wire, None, msg)
    assert mqtt.meter()["/Ac/Power"] == 0
    monkeypatch.setattr("dbus_ev.cerbo_mqtt.time.monotonic", lambda: 116)
    assert mqtt.meter() == {}
    mqtt._on_disconnect()
    assert mqtt.meter() == {}


def test_unified_charger_unknown_energy_and_away_charging():
    charger = Charger(instance=40, version="test", bus_suffix="charger")
    snap = {"ok": True, "mercedes_charging_status": 13, "at_site": True}
    charger.update(snap, {"/Ac/Power": 7200}, require_meter=True)
    assert charger.service.svc["/Status"] == 2
    assert charger.service.svc["/Ac/Power"] == 7200
    assert charger.service.svc["/Ac/Energy/Forward"] is None
    assert charger.service.svc["/Session/Energy"] is None
    charger.update(dict(snap, at_site=None), {"/Ac/Power": 7200}, require_meter=True)
    assert charger.service.svc["/Status"] == 2  # dedicated local circuit is measurable
    charger.update(dict(snap, at_site=False), {"/Ac/Power": 0}, require_meter=True)
    assert charger.service.svc["/Status"] == 0
    charger.update(snap, {}, require_meter=True)
    assert charger.service.svc["/Connected"] == 0
    assert charger.service.svc["/Ac/Power"] is None


def test_charger_state_enum_and_home_presence():
    assert charger_status(0) == 2
    assert charger_status(1) == 3
    assert charger_status(3) == 0
    assert charger_status(4) is None
    assert charger_status(16) is None
    assert at_site({"latitude": 1, "longitude": 2}, (1, 2, 100))
    assert not at_site({"latitude": 3, "longitude": 4}, (1, 2, 100))
    assert at_site({}, (1, 2, 100)) is None
