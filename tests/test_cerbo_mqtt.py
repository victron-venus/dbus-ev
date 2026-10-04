# Exercise Paho callbacks and verify the bounded internal cache without a broker.
# pylint: disable=protected-access
"""Local meter polling must not cause periodic system-wide MQTT broadcasts."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from dbus_ev.cerbo_mqtt import CerboMqtt


def broker(monkeypatch, meter=85):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("dbus_ev.cerbo_mqtt.time.monotonic", lambda: clock.now)
    wire = MagicMock()
    wire.publish.return_value.rc = 0
    mqtt = CerboMqtt(
        host="localhost", port=1883, portal="portal", meter_instance=meter, client=wire
    )
    mqtt._on_connect(wire, None, None, 0)
    return mqtt, wire, clock


def deliver(mqtt, path, value, *, retain=False):
    mqtt._on_message(
        mqtt.client,
        None,
        SimpleNamespace(
            topic="N/portal/acload/85" + path,
            payload=json.dumps({"value": value}).encode(),
            retain=retain,
        ),
    )


def test_subscribes_only_to_charger_measurements_and_bounds_cache(monkeypatch):
    mqtt, wire, _clock = broker(monkeypatch)
    topics = wire.subscribe.call_args.args[0]
    paths = {
        "/Connected",
        "/Ac/Power",
        "/Ac/Energy/Forward",
        "/Ac/Current",
        "/Ac/Frequency",
        "/Ac/L1/Power",
        "/Ac/L1/Voltage",
        "/Ac/L1/Current",
        "/Ac/L1/PowerFactor",
        "/Ac/L2/Power",
        "/Ac/L2/Voltage",
        "/Ac/L2/Current",
        "/Ac/L2/PowerFactor",
        "/Ac/L3/Power",
        "/Ac/L3/Voltage",
        "/Ac/L3/Current",
        "/Ac/L3/PowerFactor",
    }
    assert set(topics) == {("N/portal/acload/85" + path, 1) for path in paths}
    for path in paths:
        deliver(mqtt, path, 0)
    for index in range(1000):
        deliver(mqtt, f"/Diagnostics/Unused{index}", index)
    assert set(mqtt.meter()) == paths
    assert len(mqtt._meter) == 17


def test_unused_or_retained_topics_are_ignored_before_json_decode(monkeypatch):
    mqtt, _wire, _clock = broker(monkeypatch)
    decode = MagicMock(side_effect=AssertionError("unused topic was decoded"))
    monkeypatch.setattr("dbus_ev.cerbo_mqtt.json.loads", decode)
    for topic, retain in (
        ("N/portal/acload/85/Diagnostics", False),
        ("N/another-portal/acload/85/Ac/Power", False),
        ("N/portal/acload/850/Ac/Power", False),
        ("N/portal/acload/85/Ac/Power", True),
    ):
        mqtt._on_message(None, None, SimpleNamespace(topic=topic, retain=retain, payload=b"{"))
    decode.assert_not_called()
    assert mqtt.meter() == {}


def test_keepalive_never_requests_full_gx_publish_and_meter_reads_are_bounded(monkeypatch):
    mqtt, wire, clock = broker(monkeypatch)
    mqtt.tick({})
    calls = [call.args for call in wire.publish.call_args_list]
    assert calls[0] == ("R/portal/keepalive", '{"keepalive-options":["suppress-republish"]}')
    reads = set(calls[1:])
    subscriptions = wire.subscribe.call_args.args[0]
    assert len(reads) == 17
    assert reads == {("R" + topic[1:], "") for topic, _qos in subscriptions}
    assert ("R/portal/acload/85/Ac/Power", "") in reads
    assert ("R/portal/acload/85/Connected", "") in reads
    assert ("R/portal/acload/85/Ac", "") not in reads
    wire.publish.reset_mock()
    clock.now = 109
    mqtt.tick({})
    wire.publish.assert_not_called()
    for clock.now in (110, 120, 130):
        mqtt.tick({})
    calls = [call.args for call in wire.publish.call_args_list]
    assert len(calls) == 17 * 3 + 1
    for request in reads:
        assert calls.count(request) == 3
    keepalives = [payload for topic, payload in calls if topic == "R/portal/keepalive"]
    assert len(keepalives) == 1
    assert json.loads(keepalives[0]) == {"keepalive-options": ["suppress-republish"]}


def test_idle_read_responses_keep_zero_fresh_but_missing_response_expires(monkeypatch):
    mqtt, wire, clock = broker(monkeypatch)

    def read_response(topic, _payload):
        if topic == "R/portal/acload/85/Ac/Power":
            deliver(mqtt, "/Ac/Power", 0)
        elif topic == "R/portal/acload/85/Connected":
            deliver(mqtt, "/Connected", 1)

    wire.publish.side_effect = read_response
    mqtt.tick({})
    assert mqtt.meter() == {"/Ac/Power": 0, "/Connected": 1}
    clock.now = 110
    mqtt.tick({})
    clock.now = 124
    assert mqtt.meter()["/Ac/Power"] == 0
    wire.publish.side_effect = None
    clock.now = 125
    mqtt.tick({})
    assert mqtt.meter() == {}


def test_reconnect_clears_meter_and_immediately_refreshes_live_values(monkeypatch):
    mqtt, wire, clock = broker(monkeypatch)
    mqtt.tick({})
    deliver(mqtt, "/Ac/Power", 7000)
    mqtt._on_disconnect()
    assert mqtt.meter() == {}
    wire.publish.reset_mock()
    mqtt.tick({})
    wire.publish.assert_not_called()
    clock.now = 101
    mqtt._on_connect(wire, None, None, 0)
    deliver(mqtt, "/Ac/Power", 7000, retain=True)
    assert mqtt.meter() == {}
    mqtt.tick({})
    assert wire.publish.call_count == 18
    deliver(mqtt, "/Ac/Power", 0)
    assert mqtt.meter() == {"/Ac/Power": 0}


def test_disabled_meter_never_subscribes_or_requests_keepalives(monkeypatch):
    mqtt, wire, clock = broker(monkeypatch, meter=None)
    for clock.now in (100, 110, 130):
        mqtt.tick({})
    wire.subscribe.assert_not_called()
    wire.publish.assert_not_called()
