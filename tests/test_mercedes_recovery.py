"""Bounded login recovery, private storage and reuse of the sole OAuth owner."""

# pylint: disable=protected-access
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from dbus_ev.mercedes.auth import login
from dbus_ev.mercedes.client import MercedesClient
from dbus_ev.mercedes.oauth import MBAuth2FAError, MBAuthError, MBLegalTermsError
from dbus_ev.mercedes.recovery import SessionRecovery
from dbus_ev.mercedes.store import TokenStore
from tests.test_mercedes_lifecycle import VIN, Context


def credentials(tmp_path):
    path = tmp_path / "credentials.json"
    TokenStore(path).save(
        {"username": "test@example.invalid", "password": "private-password", "region": "Europe"}
    )
    return path


def test_optional_recovery_and_hourly_limit(tmp_path, monkeypatch):
    auth = MagicMock(async_login_new=AsyncMock(return_value={"access_token": "private-token"}))
    assert not asyncio.run(SessionRecovery("", "Europe").recover(auth))
    auth.async_login_new.assert_not_called()
    clock = [100.0]
    monkeypatch.setattr("dbus_ev.mercedes.recovery.time.monotonic", lambda: clock[0])
    recovery = SessionRecovery(str(credentials(tmp_path)), "Europe")
    assert asyncio.run(recovery.recover(auth))
    clock[0] = 3699
    assert not asyncio.run(recovery.recover(auth))
    auth.async_login_new.assert_awaited_once()
    clock[0] = 3700
    assert asyncio.run(recovery.recover(auth))
    assert auth.async_login_new.await_count == 2


@pytest.mark.parametrize("kind", ["public", "region", "malformed", "missing"])
def test_invalid_recovery_file_never_reaches_login(tmp_path, kind):
    path = credentials(tmp_path)
    region = "Europe"
    if kind == "public":
        path.chmod(0o644)
    elif kind == "region":
        region = "North America"
    elif kind == "malformed":
        path.write_text('{"username": 1}')
    else:
        path.unlink()
    auth = MagicMock(async_login_new=AsyncMock())
    recovery = SessionRecovery(str(path), region)
    assert not asyncio.run(recovery.recover(auth))
    auth.async_login_new.assert_not_called()
    assert recovery.failed


@pytest.mark.parametrize("error", [MBAuthError, MBAuth2FAError, MBLegalTermsError, TimeoutError])
def test_failed_login_stops_recovery_without_leaking_secrets(tmp_path, monkeypatch, caplog, error):
    auth = MagicMock(async_login_new=AsyncMock(side_effect=error("private-password private-token")))
    recovery = SessionRecovery(str(credentials(tmp_path)), "Europe")
    assert not asyncio.run(recovery.recover(auth))
    monkeypatch.setattr("dbus_ev.mercedes.recovery.time.monotonic", lambda: 1e12)
    assert not asyncio.run(recovery.recover(auth))
    auth.async_login_new.assert_awaited_once()
    assert "private-" not in caplog.text


@pytest.mark.parametrize("status,stop", [(429, False), (401, False), (429, True)])
def test_recovery_waits_for_backoff_and_uses_same_auth(tmp_path, monkeypatch, status, stop):
    client = MercedesClient(vin=VIN, region="Europe", token_file=tmp_path / "token")
    session, versions, auth = (MagicMock() for _ in range(3))
    auth.async_get_cached_token = AsyncMock(return_value={"access_token": "private-token"})
    versions.async_refresh = AsyncMock()
    session.ws_connect.side_effect = [
        aiohttp.WSServerHandshakeError(None, (), status=status, headers={"Retry-After": "1200"}),
        Context(MagicMock()),
    ]
    monkeypatch.setattr(
        "dbus_ev.mercedes.client.aiohttp.ClientSession", lambda **_: Context(session)
    )
    monkeypatch.setattr("dbus_ev.mercedes.client.AppVersionManager", lambda _: versions)
    monkeypatch.setattr("dbus_ev.mercedes.client.Oauth", lambda *_: auth)
    monkeypatch.setattr(client, "_metadata", AsyncMock(return_value={}))
    events = []

    async def cooldown(s, a, v, protocol, delay):
        assert a is auth
        if not events:
            assert delay == 1200
            events.append("waited")
            if stop:
                client._stop.set()

    async def recover(owner):
        assert owner is auth
        assert events == ["waited"]
        events.append("login")
        return True

    async def stream(*_args):
        events.append("stream")
        client._stop.set()

    monkeypatch.setattr(client, "_cooldown", cooldown)
    monkeypatch.setattr(client.recovery, "recover", recover)
    monkeypatch.setattr(client, "_stream", stream)
    asyncio.run(client._serve())
    assert events == (
        ["waited"]
        if stop
        else ["waited", "login", "stream"]
        if status == 429
        else ["waited", "stream"]
    )


@pytest.mark.parametrize("save", [False, True])
def test_standalone_login_only_stores_password_when_requested(tmp_path, monkeypatch, capsys, save):
    token = tmp_path / "token.json"
    private = tmp_path / "credentials.json"
    args = SimpleNamespace(
        token_file=str(token), region="Europe", credentials_file=str(private) if save else ""
    )
    monkeypatch.setattr(
        "dbus_ev.mercedes.auth.aiohttp.ClientSession", lambda **_: Context(MagicMock())
    )
    auth = MagicMock(async_login_new=AsyncMock())
    monkeypatch.setattr("dbus_ev.mercedes.auth.Oauth", lambda *_: auth)
    monkeypatch.setattr("builtins.input", lambda _: "test@example.invalid")
    monkeypatch.setattr("dbus_ev.mercedes.auth.getpass.getpass", lambda _: "private-password")
    asyncio.run(login(args))
    assert private.exists() is save
    if save:
        assert private.stat().st_mode & 0o777 == 0o600
        assert json.loads(private.read_text())["password"] == "private-password"
    assert "private-password" not in capsys.readouterr().out


def test_credentials_cannot_overwrite_token_file(tmp_path):
    path = str(tmp_path / "token.json")
    with pytest.raises(ValueError, match="separate files"):
        asyncio.run(login(SimpleNamespace(token_file=path, credentials_file=path)))
