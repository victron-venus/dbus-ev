"""Optional, bounded recovery of a blocked Mercedes session using existing login."""

import asyncio
import json
import logging
import os
import stat

from .traffic import LOGIN_INTERVAL, TrafficLimits, retry_delay

logger = logging.getLogger(__name__)


class SessionRecovery:
    """Reuse the sole OAuth owner after the WebSocket Retry-After has elapsed."""

    def __init__(self, credentials_file, region, limits=None):
        self.credentials_file = credentials_file
        self.region = region
        self.limits = limits or TrafficLimits(credentials_file)
        self.failed = False

    async def recover(self, auth):
        if not self.credentials_file or self.failed or not self.limits.reserve_login():
            return False
        try:
            credentials = await asyncio.to_thread(self._credentials)
            token = await auth.async_login_new(credentials["username"], credentials["password"])
            if not token or not token.get("access_token"):
                raise ValueError("No token returned")
        except Exception as exc:  # noqa: BLE001 -- preserve REST and avoid repeated failed logins
            self.failed = True
            self.limits.login_failed()
            if getattr(exc, "status", None) == 429:
                self.limits.rate_limited(exc)
            self.limits.pause(retry_delay(exc, LOGIN_INTERVAL))
            logger.warning(
                "Mercedes session recovery stopped (%s); standalone login is required",
                type(exc).__name__,
            )
            return False
        logger.info("Mercedes session recovery succeeded")
        return True

    def _credentials(self):
        # This path is explicitly configured locally, never supplied by telemetry.
        with open(self.credentials_file, encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_uid != os.geteuid()
            ):
                raise ValueError("Credentials must be private to the service user")
            credentials = json.load(stream)
        if (
            credentials.get("region") != self.region
            or not isinstance(credentials.get("username"), str)
            or not credentials["username"].strip()
            or not isinstance(credentials.get("password"), str)
            or not credentials["password"]
        ):
            raise ValueError("Invalid recovery credentials")
        return credentials
