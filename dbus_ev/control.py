"""Valve/pump control logic (pure, unit-testable).

Valve automation: open when level <= START_VALUE, close when level >=
STOP_VALUE (hysteresis). Fail-safe: stale sensor -> valve CLOSED.
Pump has no auto rules; it is driven by manual /Mode writes only.
"""

import logging
import time

logger = logging.getLogger(__name__)

# /Mode values (mirrors native Victron pump start/stop semantics)
MODE_AUTO = 0
MODE_ON = 1
MODE_OFF = 2


class ValveController:
    def __init__(
        self,
        start_value: float,
        stop_value: float,
        sensor_stale_timeout: float,
        min_switch_interval: float,
        clock=time.monotonic,
    ) -> None:
        if not stop_value > start_value:
            raise ValueError("VALVE_STOP_VALUE must be greater than VALVE_START_VALUE")
        self.start_value = start_value
        self.stop_value = stop_value
        self.sensor_stale_timeout = sensor_stale_timeout
        self.min_switch_interval = min_switch_interval
        self._clock = clock
        self.mode = MODE_AUTO
        self.last_level_time: float | None = None  # clock time of last fresh level
        self._desired: bool = False  # current commanded state
        # No transition yet -> allow the first one immediately (0.0 would
        # suppress it for min_switch_interval on hosts with small uptime).
        self._last_transition: float = self._clock() - self.min_switch_interval

    def set_mode(self, mode: int) -> None:
        if mode in (MODE_AUTO, MODE_ON, MODE_OFF):
            self.mode = mode

    def update(self, level: float | None, fresh: bool) -> tuple[bool, str]:
        """Feed latest level reading.

        Returns (desired_valve_state, reason) where reason is one of:
        'manual-on', 'manual-off', 'auto-open', 'auto-close', 'stale-close',
        'hold' (no change).
        """
        now = self._clock()
        if fresh and level is not None:
            self.last_level_time = now
        stale = (
            self.last_level_time is None or now - self.last_level_time >= self.sensor_stale_timeout
        )

        if self.mode == MODE_ON:
            return True, "manual-on"
        if self.mode == MODE_OFF:
            return False, "manual-off"

        # AUTO
        if stale:
            return False, "stale-close"

        assert level is not None
        if level <= self.start_value:
            target, why = True, "auto-open"
        elif level >= self.stop_value:
            target, why = False, "auto-close"
        else:
            return self._desired, "hold"

        # Anti-chatter: never flip faster than min_switch_interval.
        if target != self._desired and now - self._last_transition < self.min_switch_interval:
            logger.debug(
                "Suppress %s within %.0fs of last transition", why, self.min_switch_interval
            )
            return self._desired, "hold"
        if target != self._desired:
            self._last_transition = now
            self._desired = target
        return self._desired, why
