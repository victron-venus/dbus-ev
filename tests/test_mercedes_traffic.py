# Exercise network boundaries without contacting Mercedes.
# pylint: disable=protected-access
"""Account-wide cooldowns, restart persistence and bounded connection attempts."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from dbus_ev.mercedes.auth import login
from dbus_ev.mercedes.client import MercedesClient
from dbus_ev.mercedes.oauth import Oauth
from dbus_ev.mercedes.recovery import SessionRecovery
from dbus_ev.mercedes.store import TokenStore
from dbus_ev.mercedes.traffic import TrafficLimits
from dbus_ev.mercedes.vendor.app_version import AppVersionManager
from tests.test_mercedes_lifecycle import VIN, Context
from tests.test_mercedes_recovery import credentials


@pytest.fixture(name="clock")
def fake_clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("dbus_ev.mercedes.traffic.time.monotonic", lambda: now[0])
    monkeypatch.setattr("dbus_ev.mercedes.traffic.time.time", lambda: 1700000000 + now[0])
    return now


def limited(after=None):
    return aiohttp.ClientResponseError(
        None, (), status=429, headers={"Retry-After": str(after)} if after else {}
    )


def test_repeated_429_escalates_across_restarts_and_respects_longer_header(tmp_path, clock):
    path = tmp_path / "token.json"
    for delay in (1800, 3600, 7200, 14400, 21600, 21600):
        limits = TrafficLimits(path)
        assert limits.rate_limited(limited()) == delay
        assert not limits.reserve_login()
        clock[0] += delay - 1
        assert TrafficLimits(path).remaining() == 1
        clock[0] += 1
    assert limits.rate_limited(limited(86400)) == 86400
    clock[0] += 100
    assert TrafficLimits(path).remaining() == 86300
    assert limits.store.path.stat().st_mode & 0o777 == 0o600


def test_active_limit_cannot_be_reset_by_push_or_shorter_error(tmp_path, clock):
    limits = TrafficLimits(tmp_path / "token")
    limits.rate_limited(limited(86400))
    limits.healthy()
    assert limits.data["rate_retry"] == 3600
    assert limits.pause(60) == 86400
    clock[0] += 86400
    limits.healthy()
    assert limits.rate_limited(limited()) == 1800


def test_login_budget_and_failure_survive_restart_until_manual_login(tmp_path, clock):
    path = tmp_path / "token"
    limits = TrafficLimits(path)
    assert limits.reserve_login()
    assert not TrafficLimits(path).reserve_login()
    clock[0] += 21600
    assert TrafficLimits(path).reserve_login()
    limits.login_failed()
    clock[0] += 86400
    assert not TrafficLimits(path).reserve_login()
    restored = TrafficLimits(path)
    restored.manual_login_succeeded()
    assert not TrafficLimits(path).reserve_login()
    clock[0] += 21600
    assert TrafficLimits(path).reserve_login()


def test_restart_waits_before_config_auth_metadata_or_websocket(tmp_path, monkeypatch, clock):
    token = tmp_path / "token"
    TrafficLimits(token).rate_limited(limited(7200))
    client = MercedesClient(vin=VIN, region="Europe", token_file=token)
    session, auth, versions = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(
        "dbus_ev.mercedes.client.aiohttp.ClientSession", lambda **_: Context(session)
    )
    monkeypatch.setattr("dbus_ev.mercedes.client.Oauth", lambda *_: auth)
    monkeypatch.setattr("dbus_ev.mercedes.client.AppVersionManager", lambda _: versions)

    async def sleep(delay):
        assert delay == 7200
        clock[0] += delay
        client._stop.set()

    monkeypatch.setattr("dbus_ev.mercedes.client.asyncio.sleep", sleep)
    asyncio.run(client._serve())
    session.get.assert_not_called()
    session.ws_connect.assert_not_called()
    versions.async_refresh.assert_not_called()
    auth.async_get_cached_token.assert_not_called()


@pytest.mark.parametrize(
    "durations,expected", [([0, 0, 0, 0], [60, 120, 240, 480]), ([0, 301], [60, 60])]
)
def test_short_connections_do_not_reset_retry_delay(
    tmp_path, monkeypatch, clock, durations, expected
):
    client = MercedesClient(vin=VIN, region="Europe", token_file=tmp_path / "token")
    session = MagicMock()
    session.ws_connect.return_value = Context(MagicMock())
    auth = MagicMock(async_get_cached_token=AsyncMock(return_value={"access_token": "test"}))
    versions = MagicMock(async_refresh=AsyncMock())
    monkeypatch.setattr(
        "dbus_ev.mercedes.client.aiohttp.ClientSession", lambda **_: Context(session)
    )
    monkeypatch.setattr("dbus_ev.mercedes.client.Oauth", lambda *_: auth)
    monkeypatch.setattr("dbus_ev.mercedes.client.AppVersionManager", lambda _: versions)
    monkeypatch.setattr(client, "_metadata", AsyncMock(return_value={}))
    observed = []

    async def stream(*_args):
        clock[0] += durations[len(observed)]

    async def cooldown(_session, _auth, _versions, _protocol, delay):
        observed.append(delay)
        clock[0] += delay
        if len(observed) == len(expected):
            client._stop.set()

    monkeypatch.setattr(client, "_stream", stream)
    monkeypatch.setattr(client, "_cooldown", cooldown)
    asyncio.run(client._serve())
    assert observed == expected


def test_quiet_poll_waits_ten_minutes_after_each_vehicle_update(tmp_path, clock):
    client = MercedesClient(vin=VIN, region="Europe", token_file=tmp_path / "token")
    client._received = clock[0]
    assert client._pull_delay() == 600
    clock[0] += 599
    assert client._pull_delay() == 1
    client._received = clock[0]
    assert client._pull_delay() == 600


def test_blocked_cooldown_does_not_poll_at_expiry_before_recovery(tmp_path, clock, monkeypatch):
    client = MercedesClient(vin=VIN, region="Europe", token_file=tmp_path / "token")
    delay = client.limits.rate_limited(limited())
    pull = AsyncMock()
    monkeypatch.setattr(client, "_pull", pull)

    async def sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr("dbus_ev.mercedes.client.asyncio.sleep", sleep)
    asyncio.run(client._cooldown(None, None, None, None, delay))
    assert client.limits.remaining() == 0
    pull.assert_not_called()


def test_failed_persistence_prevents_credential_submission(tmp_path, monkeypatch):
    recovery = SessionRecovery(str(credentials(tmp_path)), "Europe")
    monkeypatch.setattr(recovery.limits.store, "save", MagicMock(side_effect=OSError("disk full")))
    auth = MagicMock(async_login_new=AsyncMock())
    with pytest.raises(OSError):
        asyncio.run(recovery.recover(auth))
    auth.async_login_new.assert_not_called()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1, "invalid"])
def test_corrupt_deadline_fails_closed(tmp_path, bad):
    path = tmp_path / "token"
    (tmp_path / "token.limits.json").write_text(json.dumps({"request_after": bad}))
    with pytest.raises(ValueError, match="traffic limits"):
        TrafficLimits(path)


def test_config_429_is_not_hidden_before_following_requests():
    response = MagicMock(status=429)
    response.raise_for_status.side_effect = limited(3600)
    session = MagicMock()
    session.get.return_value = Context(response)
    with pytest.raises(aiohttp.ClientResponseError) as caught:
        asyncio.run(AppVersionManager("Europe")._fetch_remote_config(session))
    assert caught.value.headers["Retry-After"] == "3600"
    session.get.assert_called_once()


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_login_steps_never_retry_transient_or_rate_limit_errors(tmp_path, status):
    async def run():
        async with aiohttp.ClientSession() as session:
            auth = Oauth(session, "Europe", TokenStore(tmp_path / "token"), MagicMock())
            response = MagicMock(status=status)
            response.raise_for_status.side_effect = aiohttp.ClientResponseError(
                None, (), status=status, headers={"Retry-After": "3600"}
            )
            auth._session = MagicMock()
            auth._session.request.return_value = Context(response)
            with pytest.raises(aiohttp.ClientResponseError):
                await auth._login_request("post", "https://example.invalid", "password")
            auth._session.request.assert_called_once()

    asyncio.run(run())


def test_token_refresh_preserves_429_retry_after(tmp_path):
    async def run():
        async with aiohttp.ClientSession() as session:
            auth = Oauth(session, "Europe", TokenStore(tmp_path / "token"), MagicMock())
            response = MagicMock(status=429)
            response.raise_for_status.side_effect = limited(86400)
            auth._session = MagicMock()
            auth._session.request.return_value = Context(response)
            with pytest.raises(aiohttp.ClientResponseError) as caught:
                await auth._async_request("post", "https://example.invalid")
            assert caught.value.headers["Retry-After"] == "86400"
            auth._session.request.assert_called_once()

    asyncio.run(run())


def test_login_429_blocks_every_endpoint_and_survives_restart(tmp_path, clock):
    token = tmp_path / "token"
    limits = TrafficLimits(token)
    recovery = SessionRecovery(str(credentials(tmp_path)), "Europe", limits)
    auth = MagicMock(async_login_new=AsyncMock(side_effect=limited(86400)))
    assert not asyncio.run(recovery.recover(auth))
    restored = TrafficLimits(token)
    assert restored.remaining() == 86400
    clock[0] += 86400
    assert not restored.reserve_login()


def test_standalone_login_does_not_bypass_pause_or_prompt(tmp_path, monkeypatch, clock):
    token = tmp_path / "token"
    TrafficLimits(token).rate_limited(limited())
    prompt = MagicMock()
    monkeypatch.setattr("builtins.input", prompt)
    args = SimpleNamespace(token_file=str(token), region="Europe")
    with pytest.raises(ValueError, match="cooldown"):
        asyncio.run(login(args))
    prompt.assert_not_called()
