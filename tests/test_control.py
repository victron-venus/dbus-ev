"""Tests for ValveController logic using a fake clock."""

import pytest

from dbus_ev.control import MODE_AUTO, MODE_OFF, MODE_ON, ValveController


class FakeClock:
    """Simple clock that advances time and supports __call__ for time reads."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture(name="clock")
def clock_factory():
    return FakeClock()


def _make_controller(clock):
    return ValveController(
        start_value=30.0,
        stop_value=85.0,
        sensor_stale_timeout=120.0,
        min_switch_interval=60.0,
        clock=clock,
    )


def test_opens_below_start(clock):
    c = _make_controller(clock)
    desired, why = c.update(20.0, fresh=True)
    assert desired is True and why == "auto-open"


def test_closes_above_stop(clock):
    c = _make_controller(clock)
    c.update(20.0, True)
    clock.advance(120)
    desired, why = c.update(90.0, fresh=True)
    assert desired is False and why == "auto-close"


def test_hysteresis_hold_between_thresholds(clock):
    c = _make_controller(clock)
    c.update(20.0, True)
    clock.advance(120)
    desired, why = c.update(50.0, fresh=True)
    assert desired is True and why == "hold"


def test_stale_sensor_forces_close(clock):
    c = _make_controller(clock)
    c.update(20.0, True)
    clock.advance(121)  # beyond stale timeout, no fresh reading since open
    desired, why = c.update(None, fresh=False)
    assert desired is False and why == "stale-close"


def test_never_fresh_means_immediate_stale_close(clock):
    c = _make_controller(clock)
    desired, why = c.update(None, fresh=False)
    assert desired is False and why == "stale-close"


def test_anti_chatter_suppresses_flip(clock):
    c = _make_controller(clock)
    c.update(20.0, True)  # open at t=1000
    clock.advance(10)  # only 10s later
    desired, why = c.update(90.0, fresh=True)
    assert desired is True and why == "hold"


def test_manual_on_overrides_auto(clock):
    c = _make_controller(clock)
    c.set_mode(MODE_ON)
    desired, why = c.update(95.0, fresh=True)
    assert desired is True and why == "manual-on"


def test_manual_off_overrides_low_level(clock):
    c = _make_controller(clock)
    c.set_mode(MODE_OFF)
    desired, why = c.update(5.0, fresh=True)
    assert desired is False and why == "manual-off"


def test_back_to_auto_resumes_logic(clock):
    c = _make_controller(clock)
    c.set_mode(MODE_OFF)
    c.update(10.0, True)
    c.set_mode(MODE_AUTO)
    desired, why = c.update(95.0, fresh=True)
    assert desired is False and why == "auto-close"


def test_invalid_thresholds_rejected():
    with pytest.raises(ValueError, match="VALVE_STOP_VALUE must be greater than VALVE_START_VALUE"):
        ValveController(85.0, 30.0, sensor_stale_timeout=120.0, min_switch_interval=60.0)


def test_mode_constants_match_victron():
    assert MODE_AUTO == 0
    assert MODE_ON == 1
    assert MODE_OFF == 2
