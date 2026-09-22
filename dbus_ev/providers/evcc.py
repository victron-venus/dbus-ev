"""One persistent, read-only evcc engine; conservative scheduling survives restart."""

import argparse
import json
import logging
import math
import os
import selectors
import stat
import subprocess
import time
from pathlib import Path

from dbus_ev.mercedes.store import TokenStore
from dbus_ev.vehicle import normalize, number

logger = logging.getLogger(__name__)
MIN_INTERVAL = 1800
LOGIN_INTERVAL = 21600
MAX_REPLY = 65536


class Engine:
    """Bounded local pipe protocol. Credentials never appear in command arguments."""

    def __init__(self, binary, config_file, database, timeout=90):
        self.timeout = timeout
        # The process intentionally lives across polls and is reaped in close().
        self.process = subprocess.Popen(  # pylint: disable=consider-using-with
            [binary, f"--config={config_file}", f"--database={database}"],
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            # No inherited evcc render/debug overrides: those can print credentials.
            env={key: value for key, value in os.environ.items() if not key.startswith("EVCC_")},
            bufsize=0,
        )
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def poll(self):
        self.process.stdin.write(b"poll\n")
        deadline = time.monotonic() + self.timeout
        content = bytearray()
        while len(content) <= MAX_REPLY:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError("Vehicle engine did not reply")
            chunk = os.read(self.process.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError("Vehicle engine exited")
            content.extend(chunk)
            if b"\n" in chunk:
                if len(content) > MAX_REPLY:
                    break
                response = json.loads(content)
                if not isinstance(response, dict) or response.get("schema") != 1:
                    raise ValueError("Unsupported vehicle engine response")
                return response
        raise ValueError("Vehicle engine response too large")

    def close(self):
        self.selector.close()
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process.stdout.close()


class EvccClient:
    """Reuse one provider instance; frequent local reads never trigger cloud polls."""

    def __init__(
        self,
        *,
        binary,
        config_file,
        state_file,
        interval=3600,
        stale_timeout=7500,
        capacity=None,
        home=(None, None, 150),
        engine_factory=Engine,
    ):
        self.config_file = Path(config_file)
        mode = self.config_file.stat().st_mode
        if not stat.S_ISREG(mode) or stat.S_IMODE(mode) & 0o077:
            raise ValueError("EVCC_CONFIG_FILE must be a private regular file (chmod 600)")
        conf = json.loads(self.config_file.read_text(encoding="utf-8"))
        self.template = conf.get("template")
        self.vin = str(conf.get("vin", "")).upper()
        if (
            self.template == "niu-e-scooter"
            and isinstance(conf.get("serial"), str)
            and conf["serial"]
        ):
            self.vin = None
        elif (
            not self.template
            or len(self.vin) != 17
            or not self.vin.isascii()
            or not self.vin.isalnum()
        ):
            raise ValueError("EVCC_CONFIG_FILE requires a template and explicit 17-character VIN")
        if not os.path.isfile(binary) or not os.access(binary, os.X_OK):
            raise ValueError("Build/install the optional dbus-ev vehicle engine first")
        if not math.isfinite(float(interval)):
            raise ValueError("EVCC intervals must be finite")
        self.interval = max(MIN_INTERVAL, float(interval))
        if self.template == "cardata":
            self.interval = max(3600, self.interval)
        self.stale_timeout = float(stale_timeout)
        if not all(map(math.isfinite, (self.interval, self.stale_timeout))):
            raise ValueError("EVCC intervals must be finite")
        if self.stale_timeout <= self.interval:
            raise ValueError("EVCC_STALE_TIMEOUT must exceed the effective poll interval")
        self.binary, self.factory = binary, engine_factory
        self.store = TokenStore(state_file, owner="vehicle engine")
        self.database = str(state_file) + ".db"
        self.capacity, self.home = capacity, home
        self.engine = None
        self.started = False
        self.snapshot = {"ok": False}
        self.received = None
        self.sampled_at = None

    def start(self):
        if not self.started:
            self.store.acquire()
            self.started = True

    def _save(self, **changes):
        self.store.save(dict(self.store.data, **changes))

    def _failure(self, response):
        kind = response.get("error", "provider")
        failures = min(5, int(self.store.data.get("failures", 0)) + 1)
        delay = max(self.interval, min(LOGIN_INTERVAL, 1800 * 2 ** (failures - 1)))
        delay = max(delay, number(response.get("retry_after"), 0) or 0)
        # Failed authorization or configuration requires operator intervention.
        blocked = kind in ("auth", "configuration", "storage")
        self._save(next_poll=time.time() + delay, failures=failures, blocked=blocked)
        logger.warning(
            "Vehicle provider unavailable (%s); %s",
            kind,
            "manual recovery required" if blocked else f"retry after {int(delay)}s",
        )
        if blocked or kind == "rate_limit":
            self._stop_engine()

    def _stop_engine(self):
        if self.engine is not None:
            self.engine.close()
            self.engine = None

    def _poll_engine(self, now):
        # Reserve before network I/O so process crashes cannot bypass pacing.
        self._save(next_poll=now + self.interval)
        if self.engine is None:
            self._save(next_login=now + LOGIN_INTERVAL)
        started_at = time.monotonic()
        try:
            if self.engine is None:
                self.engine = self.factory(self.binary, self.config_file, self.database)
            response = self.engine.poll()
            if response.get("ok") is True and isinstance(response.get("data"), dict):
                candidate = normalize(
                    response["data"], vin=self.vin, capacity=self.capacity, home=self.home
                )
                if candidate["soc"] is None:
                    raise ValueError("Missing valid state of charge")
                self.snapshot = candidate
                self.received, self.sampled_at = started_at, now
                self._save(failures=0, next_poll=time.time() + self.interval)
            else:
                self._failure(response)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError):
            # Do not log provider output or exception bodies.
            self._stop_engine()
            self._failure({"error": "transport"})

    def poll(self):
        self.start()
        now = time.time()
        state = self.store.data
        if (
            not state.get("blocked")
            and now >= state.get("next_poll", 0)
            and (self.engine is not None or now >= state.get("next_login", 0))
        ):
            self._poll_engine(now)
        fresh = (
            self.received is not None and 0 <= time.monotonic() - self.received < self.stale_timeout
        )
        return dict(
            self.snapshot,
            ok=fresh,
            _source_sample_started_at=self.received,
            sampled_at=self.sampled_at,
            source=f"evcc:{self.template}",
        )

    def close(self):
        self._stop_engine()
        self.store.close()
        self.started = False


def main():
    """Explicit operator recovery; never called by the running daemon."""
    parser = argparse.ArgumentParser(description="Authorize an experimental vehicle provider")
    parser.add_argument("--binary", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--state-file", required=True)
    args = parser.parse_args()
    store = TokenStore(args.state_file, owner="vehicle engine")
    store.acquire()
    try:
        # S8701/S8705: this local operator CLI deliberately selects the installed
        # engine with the operator's own privileges, never from vehicle telemetry
        # or a network endpoint. Separate argv and flag=value preserve literal paths.
        result = subprocess.run(  # NOSONAR - reviewed local executable selection
            [
                args.binary,
                f"--config={args.config}",
                f"--database={args.state_file}.db",
                "--authorize",
            ],
            shell=False,
            check=False,
        )
        if result.returncode == 0:
            store.save(dict(store.data, blocked=False, failures=0, next_poll=0, next_login=0))
        return result.returncode
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
