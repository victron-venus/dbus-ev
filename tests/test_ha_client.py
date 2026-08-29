import json
from unittest.mock import MagicMock, patch

from dbus_pump.ha_client import CircuitBreaker, HaClient, build_template, state_is_on


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def make_client(**kw):
    defaults = {
        "base_url": "http://ha:8123",
        "token": "tok",
        "level_entity": "sensor.level",
        "pump_entity": "switch.pump",
        "valve_entity": "switch.valve",
        "cm_entity": "sensor.water_cm",
        "timeout": 3.0,
    }
    defaults.update(kw)
    return HaClient(**defaults)


def template_response(level="42.0", pump="on", valve="off", cm="82.5"):
    payload = {"level": level, "pump": pump, "valve": valve, "cm": cm}
    resp = MagicMock(status_code=200, text=json.dumps(payload))
    return resp


def test_build_template_contains_entities():
    t = build_template("s.l", "s.p", "s.v")
    assert "states('s.l')" in t and "'pump': states('s.p')" in t and "'valve': states('s.v')" in t
    # no raw-height entity -> placeholder id, still valid Jinja for HA
    assert "states('__no_cm_sensor__')" in t


def test_build_template_cm_entity():
    t = build_template("s.l", "s.p", "s.v", "sensor.water_cm")
    assert "states('sensor.water_cm')" in t


def test_state_is_on_mapping():
    assert state_is_on("on") is True
    assert state_is_on("running") is True
    assert state_is_on("off") is False
    assert state_is_on("unavailable") is None
    assert state_is_on("unknown") is None
    assert state_is_on("") is None


@patch("dbus_pump.ha_client.requests.Session.post")
def test_poll_success(post):
    post.return_value = template_response()
    c = make_client()
    r = c.poll()
    assert r["ok"] is True and r["level"] == 42.0
    assert r["cm"] == 82.5
    assert r["pump"] is True and r["valve"] is False
    args, kwargs = post.call_args
    assert args[0] == "http://ha:8123/api/template"
    assert "states('sensor.level')" in kwargs["json"]["template"]
    assert "states('sensor.water_cm')" in kwargs["json"]["template"]


@patch("dbus_pump.ha_client.requests.Session.post")
def test_poll_cm_unavailable_is_none_but_ok(post):
    post.return_value = template_response(cm="unknown", level="50.0")
    c = make_client()
    r = c.poll()
    assert r["ok"] is True and r["cm"] is None


@patch("dbus_pump.ha_client.requests.Session.post")
def test_poll_nonnumeric_level_marks_not_ok(post):
    post.return_value = template_response(level="unavailable")
    c = make_client()
    r = c.poll()
    assert r["ok"] is False and r["level"] is None


@patch("dbus_pump.ha_client.requests.Session.post")
def test_poll_failure_serves_last_known(post):
    post.return_value = template_response()
    c = make_client()
    first = c.poll()
    assert first["ok"] is True

    from requests.exceptions import Timeout

    post.side_effect = Timeout("boom")
    second = c.poll()
    assert second["ok"] is False
    assert second["level"] == 42.0  # last-known served
    assert second["pump"] is True


@patch("dbus_pump.ha_client.requests.Session.post")
def test_circuit_breaker_opens_and_resets(post, monkeypatch=None):
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=3, reset_timeout=60.0)

    # drive the clock used inside the breaker by patching time.monotonic
    import dbus_pump.ha_client as mod

    real_monotonic = mod.time.monotonic
    mod.time.monotonic = lambda: clock.t

    try:
        from requests.exceptions import ConnectionError as ReqConnError

        post.side_effect = ReqConnError("down")
        c = make_client(breaker=breaker)
        for _ in range(3):
            c.poll()
        assert breaker.is_open is True
        # while open, poll does not even hit the network
        calls_before = post.call_count
        c.poll()
        assert post.call_count == calls_before

        clock.advance(61)  # past reset timeout -> half-open allows one attempt
        assert breaker.is_open is False
        post.side_effect = None
        post.return_value = template_response()
        r = c.poll()
        assert r["ok"] is True
        assert breaker.is_open is False
    finally:
        mod.time.monotonic = real_monotonic


@patch("dbus_pump.ha_client.requests.Session.post")
def test_call_service_success_and_failure(post):
    c = make_client()
    post.return_value = MagicMock(status_code=200)
    assert c.call_service("switch", "turn_on", "switch.valve") is True
    assert post.call_args[0][0].endswith("/api/services/switch/turn_on")

    post.return_value = MagicMock(status_code=500)
    assert c.call_service("switch", "turn_off", "switch.valve") is False


@patch("dbus_pump.ha_client.requests.Session.post")
def test_unconfigured_client_shortcircuits(post):
    c = HaClient(base_url="", token="", level_entity="l", pump_entity="p", valve_entity="v")
    r = c.poll()
    assert r["ok"] is False
    assert post.call_count == 0
