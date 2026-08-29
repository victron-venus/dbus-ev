import json
from unittest.mock import MagicMock, patch

import pytest

from dbus_ev.ha_client import CircuitBreaker, HaClient, _is_ha_entity, build_template, state_is_on


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
        "soc_entity": "sensor.soc",
        "target_soc_entity": "sensor.target_soc",
        "vin_entity": "sensor.vin",
        "battery_capacity_entity": "sensor.battery_capacity",
        "charging_state_entity": "sensor.charging_state",
        "odometer_entity": "sensor.odometer",
        "range_to_go_entity": "sensor.range_to_go",
        "latitude_entity": "sensor.latitude",
        "longitude_entity": "sensor.longitude",
        "at_site_entity": "sensor.at_site",
        "timeout": 3.0,
    }
    defaults.update(kw)
    return HaClient(**defaults)


def template_response(
    soc="42.0",
    target_soc="80",
    vin="123456789",
    battery_capacity="75.5",
    charging_state="charging",
    odometer="15000",
    range_to_go="30.5",
    latitude="37.7749",
    longitude="-122.4194",
    at_site="on",
):
    payload = {
        "soc": soc,
        "target_soc": target_soc,
        "vin": vin,
        "battery_capacity": battery_capacity,
        "charging_state": charging_state,
        "odometer": odometer,
        "range_to_go": range_to_go,
        "latitude": latitude,
        "longitude": longitude,
        "at_site": at_site,
    }
    resp = MagicMock(status_code=200, text=json.dumps(payload))
    return resp


def test_build_template_contains_entities():
    t = build_template(
        "sensor.soc",
        "sensor.target_soc",
        "sensor.vin",
        "sensor.battery_capacity",
        "sensor.charging_state",
        "sensor.odometer",
        "sensor.range_to_go",
        "sensor.latitude",
        "sensor.longitude",
        "sensor.at_site",
    )
    assert "'soc': states('sensor.soc')" in t
    # Optional entities use ternary (x if cond else y) inside the dict literal
    assert (
        "'target_soc': states('sensor.target_soc') | string if 'sensor.target_soc' != '' else none"
        in t
    )
    assert "'vin': states('sensor.vin') | string if 'sensor.vin' != '' else ''" in t


def test_build_template_empty_optional_entities():
    """Empty optional entities produce 'none' literal in template."""
    t = build_template(
        "sensor.soc",
        "",
        "sensor.vin",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    )
    assert "'soc': states('sensor.soc')" in t
    # Empty target_soc -> ternary takes the else branch (none).
    assert "'target_soc': states('') | string if '' != '' else none" in t
    # Non-empty entity id (sensor.vin) selects the states() branch.
    assert "'vin': states('sensor.vin') | string if 'sensor.vin' != '' else ''" in t


def test_is_ha_entity_recognizes_domain_object_id():
    assert _is_ha_entity("sensor.mercedes_vin") is True
    assert _is_ha_entity("binary_sensor.foo") is True
    assert _is_ha_entity("input_text.bar") is True
    # Static VIN-like strings (no domain.object_id pattern) are NOT entity ids.
    assert _is_ha_entity("4JGDM0EB0PA123456") is False
    assert _is_ha_entity("WBA123456789") is False
    assert _is_ha_entity("") is False


def test_build_template_static_vin_emits_literal():
    """VIN without domain.object_id -> JSON string literal, no states() call."""
    t = build_template(
        "sensor.soc",
        "",
        "4JGDM0EB0PA123456",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    )
    # Literal branch selected, no states() call for VIN.
    assert "'vin': states('') | string if '' != '' else '4JGDM0EB0PA123456'" in t
    assert "states('4JGDM0EB0PA123456')" not in t


def test_build_template_entity_vin_uses_states():
    """VIN with domain.object_id -> states() call (HA lookup)."""
    t = build_template(
        "sensor.soc",
        "",
        "sensor.mercedes_vin",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    )
    assert (
        "'vin': states('sensor.mercedes_vin') | string if 'sensor.mercedes_vin' != '' else ''" in t
    )


def test_build_template_renders_in_jinja():
    """Rendered template must parse in real Jinja2 — proves the expression
    is well-formed (the fix for /api/template 400)."""
    jinja2 = pytest.importorskip("jinja2")
    from jinja2 import Environment

    t = build_template(
        "sensor.soc",
        "",
        "4JGDM0EB0PA123456",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
    )
    # Parse-only: if Jinja can compile the rendered template, HA's Jinja
    # (a strict subset) will accept it. HA's `states`/`to_json` filters
    # live in HA's env; we don't render here.
    Environment().parse(t)


@patch("dbus_ev.ha_client.requests.Session.post")
def test_poll_static_vin_uses_literal_no_ha_call_for_vin(post):
    """Static VIN: client never asks HA to resolve it; VIN returned as string."""
    c = make_client(vin_entity="4JGDM0EB0PA123456")
    # HA returns the embedded literal verbatim.
    post.return_value = template_response(soc="55.0", vin="4JGDM0EB0PA123456")
    r = c.poll()
    assert r["ok"] is True
    assert r["vin"] == "4JGDM0EB0PA123456"
    # The Jinja sent to HA must NOT contain states('4JGDM0EB0PA123456').
    sent_template = post.call_args.kwargs["json"]["template"]
    assert "states('4JGDM0EB0PA123456')" not in sent_template


def test_state_is_on_mapping():
    assert state_is_on("on") is True
    assert state_is_on("off") is False
    assert state_is_on("unavailable") is None
    assert state_is_on("unknown") is None
    assert state_is_on("") is None
    assert state_is_on(None) is None


@patch("dbus_ev.ha_client.requests.Session.post")
def test_poll_success(post):
    post.return_value = template_response()
    c = make_client()
    r = c.poll()
    assert r["ok"] is True
    assert r["soc"] == 42.0
    assert r["target_soc"] == 80.0
    assert r["vin"] == "123456789"
    args, kwargs = post.call_args
    assert args[0] == "http://ha:8123/api/template"
    assert "states('sensor.soc')" in kwargs["json"]["template"]


@patch("dbus_ev.ha_client.requests.Session.post")
def test_poll_empty_optional_entities_return_none(post):
    """Empty optional entities -> poll returns None for those fields."""
    c = make_client(
        target_soc_entity="",
        vin_entity="",
        battery_capacity_entity="",
        charging_state_entity="",
        odometer_entity="",
        range_to_go_entity="",
        latitude_entity="",
        longitude_entity="",
        at_site_entity="",
    )
    # HA returns "none" for empty optional entities
    post.return_value = template_response(
        soc="90.0",
        target_soc="none",
        vin="none",
        battery_capacity="none",
        charging_state="none",
        odometer="none",
        range_to_go="none",
        latitude="none",
        longitude="none",
        at_site="none",
    )
    r = c.poll()
    assert r["ok"] is True
    assert r["soc"] == 90.0
    assert r["target_soc"] is None
    assert r["vin"] is None
    assert r["battery_capacity"] is None
    assert r["charging_state"] is None
    assert r["odometer"] is None
    assert r["range_to_go"] is None
    assert r["latitude"] is None
    assert r["longitude"] is None
    assert r["at_site"] is None


@patch("dbus_ev.ha_client.requests.Session.post")
def test_poll_failure_serves_last_known(post):
    post.return_value = template_response()
    c = make_client()
    first = c.poll()
    assert first["ok"] is True

    from requests.exceptions import Timeout

    post.side_effect = Timeout("boom")
    second = c.poll()
    assert second["ok"] is False
    assert second["soc"] == 42.0  # last-known served


@patch("dbus_ev.ha_client.requests.Session.post")
def test_circuit_breaker_opens_and_resets(post):
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=3, reset_timeout=60.0)

    import dbus_ev.ha_client as mod

    real_monotonic = mod.time.monotonic
    mod.time.monotonic = lambda: clock.t

    try:
        from requests.exceptions import ConnectionError as ReqConnError

        post.side_effect = ReqConnError("down")
        c = make_client(breaker=breaker)
        for _ in range(3):
            c.poll()
        assert breaker.is_open is True
        calls_before = post.call_count
        c.poll()
        assert post.call_count == calls_before

        clock.advance(61)
        assert breaker.is_open is False
        post.side_effect = None
        post.return_value = template_response()
        r = c.poll()
        assert r["ok"] is True
        assert breaker.is_open is False
    finally:
        mod.time.monotonic = real_monotonic


@patch("dbus_ev.ha_client.requests.Session.post")
def test_unconfigured_client_shortcircuits(post):
    c = HaClient(
        base_url="",
        token="",
        soc_entity="sensor.soc",
        target_soc_entity="",
        vin_entity="",
        battery_capacity_entity="",
        charging_state_entity="",
        odometer_entity="",
        range_to_go_entity="",
        latitude_entity="",
        longitude_entity="",
        at_site_entity="",
    )
    r = c.poll()
    assert r["ok"] is False
    assert c._configured is False
    assert post.call_count == 0
