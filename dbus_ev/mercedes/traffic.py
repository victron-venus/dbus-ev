"""Persistent request limits shared by the one Mercedes OAuth/telemetry owner."""

import math
import time
from email.utils import parsedate_to_datetime

from .store import TokenStore

RATE_LIMIT_MIN = 1800
RATE_LIMIT_MAX = 21600
LOGIN_INTERVAL = 21600


def retry_delay(error, minimum):
    """Respect Retry-After seconds or HTTP dates without shortening our delay."""
    value = (getattr(error, "headers", None) or {}).get("Retry-After")
    if value is None:
        return minimum
    try:
        delay = float(value)
    except (TypeError, ValueError):
        try:
            delay = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return minimum
    return max(minimum, delay) if math.isfinite(delay) else minimum


class TrafficLimits:
    """Persist deadlines before requests; a restart cannot bypass server limits."""

    def __init__(self, token_file):
        self.store = TokenStore(str(token_file) + ".limits.json")
        self.data = self.store.data
        if not isinstance(self.data, dict):
            raise TypeError("Invalid persisted Mercedes traffic limits")
        for key in ("request_after", "login_after", "rate_retry"):
            value = self.data.get(key, 0)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid persisted Mercedes traffic limits")
        remaining = max(0, self.data.get("request_after", 0) - time.time())
        self.deadline = time.monotonic() + remaining if remaining else 0
        remaining = max(0, self.data.get("login_after", 0) - time.time())
        self.login_deadline = time.monotonic() + remaining if remaining else 0

    def remaining(self):
        return max(0, self.deadline - time.monotonic())

    def pause(self, delay):
        delay = max(delay, self.remaining())
        self.deadline = time.monotonic() + delay
        self.data["request_after"] = time.time() + delay
        self.store.save(self.data)
        return delay

    def rate_limited(self, error):
        minimum = max(RATE_LIMIT_MIN, self.data.get("rate_retry", RATE_LIMIT_MIN))
        self.data["rate_retry"] = min(minimum * 2, RATE_LIMIT_MAX)
        return self.pause(retry_delay(error, minimum))

    def healthy(self):
        """Only a sustained live stream can reset the escalating 429 backoff."""
        if not self.remaining() and self.data.get("rate_retry", RATE_LIMIT_MIN) != RATE_LIMIT_MIN:
            self.data["rate_retry"] = RATE_LIMIT_MIN
            self.store.save(self.data)

    def reserve_login(self):
        if (
            self.remaining()
            or self.data.get("login_failed", False)
            or time.monotonic() < self.login_deadline
        ):
            return False
        self.login_deadline = time.monotonic() + LOGIN_INTERVAL
        self.data["login_after"] = time.time() + LOGIN_INTERVAL
        # Persist before sending credentials, including across a crash/restart.
        self.store.save(self.data)
        return True

    def login_failed(self):
        self.data["login_failed"] = True
        self.store.save(self.data)

    def manual_login_succeeded(self):
        self.data["login_failed"] = False
        self.login_deadline = time.monotonic() + LOGIN_INTERVAL
        self.data["login_after"] = time.time() + LOGIN_INTERVAL
        self.store.save(self.data)
