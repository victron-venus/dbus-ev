"""Verify batched unit metadata and numeric output validity without networking."""

import json
from unittest.mock import MagicMock, patch

import pytest

from dbus_ev.ha_client import CircuitBreaker, map_charging_state
from tests.test_ha_client import make_client
from tests.test_service import make_ev_services


def mocked_client():
    session = MagicMock()
    with patch("dbus_ev.ha_client.requests.Session", return_value=session):
        client = make_client(breaker=CircuitBreaker(threshold=1))
    return client, session


@pytest.mark.parametrize(
    "unit,power,expected", [("W", "9500", 9500), ("kW", "9.5", 9500), (None, "9.5", 9500)]
)
def test_one_template_request_preserves_power_and_distance_units(unit, power, expected):
    client, session = mocked_client()
    session.post = MagicMock(
        return_value=MagicMock(
            status_code=200,
            text=json.dumps(
                {
                    "soc": "42",
                    "power": power,
                    "power_unit": unit,
                    "odometer": "100",
                    "odometer_unit": "mi",
                    "range_to_go": "50",
                    "range_to_go_unit": "km",
                }
            ),
        )
    )
    session.get = MagicMock(side_effect=AssertionError("separate metadata HTTP read"))
    result = client.poll()
    assert result["power"] == expected
    assert result["odometer"] == pytest.approx(160.9344)
    assert result["range_to_go"] == 50
    session.post.assert_called_once()
    session.get.assert_not_called()
    assert (
        "state_attr('sensor.power', 'unit_of_measurement')"
        in session.post.call_args.kwargs["json"]["template"]
    )


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_numbers_are_invalid_without_resetting_success(invalid):
    client, session = mocked_client()
    session.post = MagicMock(
        return_value=MagicMock(
            status_code=200,
            text=json.dumps(
                {
                    "soc": invalid,
                    "power": invalid,
                    "odometer": invalid,
                }
            ),
        )
    )
    result = client.poll()
    assert result["ok"] is False
    assert result["soc"] is None
    assert result["power"] is None
    assert result["odometer"] is None


@pytest.mark.parametrize("payload", [None, [], 42])
def test_nonobject_template_reply_is_failed_poll(payload):
    client, session = mocked_client()
    session.post = MagicMock(return_value=MagicMock(status_code=200, text=json.dumps(payload)))
    assert client.poll()["ok"] is False
    assert client.breaker.is_open


@pytest.mark.parametrize(
    "state,expected", [("charging", 3), ("discharging", 256), ("unexpected", 255), ("0", 3)]
)
def test_charging_state_always_maps_to_an_integer(state, expected):
    assert map_charging_state(state) == expected


@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), 2**40])
def test_invalid_power_clears_previous_dbus_value_and_recovers(invalid):
    service = make_ev_services()
    service.update_ac_power(120)
    service.update_ac_power(invalid)
    assert service.ev["/Ac/Power"] is None
    assert service.ev["/Ac/L1/Power"] is None
    service.update_ac_power(0)
    assert service.ev["/Ac/Power"] == 0
