# Exercise callback boundaries and failure states without a live cloud connection.
# pylint: disable=protected-access
"""Exercise the network lifecycle without credentials or vehicle commands."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from dbus_ev import config
from dbus_ev.main import build_app
from dbus_ev.mercedes.client import MercedesClient
from dbus_ev.mercedes.oauth import Oauth
from dbus_ev.mercedes.store import TokenStore
from dbus_ev.mercedes.vendor.proto import vehicle_events_pb2

VIN = "WDD00000000000001"


class Context:
    """Context implementation."""

    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False


def test_websocket_one_owner_ack_and_shutdown(monkeypatch, tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    message = vehicle_events_pb2.PushMessage()
    message.vepUpdates.sequence_number = 22
    car = message.vepUpdates.updates[VIN]
    car.vin, car.full_update = VIN, True
    car.attributes["soc"].int_value = 72
    received = []

    class Socket:
        """Socket implementation."""

        async def send_bytes(self, data):
            received.append(data)

        def __aiter__(self):
            return self.messages()

        async def messages(self):
            yield SimpleNamespace(type=aiohttp.WSMsgType.BINARY, data=message.SerializeToString())
            assert client.poll()["soc"] == 72
            assert client.poll()["ok"]
            client._stop.set()

    session = MagicMock()
    session.ws_connect.return_value = Context(Socket())
    versions = MagicMock()
    versions.async_refresh = AsyncMock()
    versions.apply_websocket_headers.side_effect = lambda headers: headers
    auth = MagicMock()
    auth.async_get_cached_token = AsyncMock(return_value={"access_token": "never-publish"})
    monkeypatch.setattr(
        "dbus_ev.mercedes.client.aiohttp.ClientSession", lambda **_: Context(session)
    )
    monkeypatch.setattr("dbus_ev.mercedes.client.AppVersionManager", lambda _: versions)
    monkeypatch.setattr("dbus_ev.mercedes.client.Oauth", lambda *_: auth)
    monkeypatch.setattr(client, "_metadata", AsyncMock(return_value={"name": "Test"}))
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr("dbus_ev.mercedes.client.asyncio.sleep", sleep)
    asyncio.run(client._serve())
    assert session.ws_connect.call_count == 1
    assert len(received) == 1
    assert client.poll()["ok"] is False
    assert "never-publish" not in json.dumps(client.poll())
    assert not sleeps


def test_auth_failure_backs_off_and_does_not_login(monkeypatch, tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    session, versions = MagicMock(), MagicMock()
    versions.async_refresh = AsyncMock()
    auth = MagicMock()
    auth.async_get_cached_token = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "dbus_ev.mercedes.client.aiohttp.ClientSession", lambda **_: Context(session)
    )
    monkeypatch.setattr("dbus_ev.mercedes.client.AppVersionManager", lambda _: versions)
    monkeypatch.setattr("dbus_ev.mercedes.client.Oauth", lambda *_: auth)
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        client._stop.set()

    monkeypatch.setattr("dbus_ev.mercedes.client.asyncio.sleep", sleep)
    asyncio.run(client._serve())
    session.ws_connect.assert_not_called()
    auth.async_login_new.assert_not_called()
    assert 21599 <= sleeps[0] <= 21600


def test_quiet_socket_survives_stale_deadline_and_cancels_reader(monkeypatch, tmp_path):
    client = MercedesClient(
        vin=VIN, region="North America", token_file=tmp_path / "token", stale_timeout=0.01
    )
    closed = []

    class QuietSocket:
        """A responsive transport with no changed vehicle values."""

        def __aiter__(self):
            return self.messages()

        async def messages(self):
            try:
                await asyncio.Event().wait()
                yield
            finally:
                closed.append(True)

    async def run():
        client._next_pull = __import__("time").monotonic() + 0.04

        async def pull(*_args):
            # We have passed the old 0.01 s vehicle deadline without closing WS.
            assert not closed
            assert not client.poll()["ok"]
            client._stop.set()

        monkeypatch.setattr(client, "_pull", pull)
        await asyncio.wait_for(client._stream(QuietSocket(), None, None, None, None), 1)

    asyncio.run(run())
    assert closed == [True]


def test_login_error_does_not_expose_server_body(tmp_path, caplog):
    async def run():
        async with aiohttp.ClientSession() as session:
            auth = Oauth(session, "North America", TokenStore(tmp_path / "token"), MagicMock())
            auth._get_authorization_resume = AsyncMock(return_value="/resume")
            auth._send_user_agent_info = AsyncMock()
            auth._submit_username = AsyncMock()
            auth._submit_password = AsyncMock(
                return_value={"result": "ERROR", "token": "private-token", "email": "private-email"}
            )
            with pytest.raises(Exception, match="verify the account") as error:
                await auth.async_login_new("private-email", "private-password")
            assert "private-" not in str(error.value)

    asyncio.run(run())
    assert "private-" not in caplog.text


def test_metadata_only_copies_vehicle_display_fields(tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    versions = MagicMock()
    versions.apply_webapi_headers.side_effect = lambda headers: headers
    response1, response2 = MagicMock(), MagicMock()
    response1.json = AsyncMock(
        return_value={
            "assignedVehicles": [
                {
                    "vin": VIN,
                    "licensePlate": "Test",
                    "isOwner": True,
                    "salesRelatedInformation": {"baumuster": {"baumusterDescription": "EQ"}},
                    "account_email": "private@example.invalid",
                }
            ]
        }
    )
    response2.json = AsyncMock(
        return_value={"vehicle": {"headUnitType": "test", "secret": "discard"}}
    )
    session = MagicMock()
    session.get.side_effect = [Context(response1), Context(response2)]
    metadata = asyncio.run(client._metadata(session, {"access_token": "secret"}, versions))
    assert metadata == {
        "name": "Test",
        "model": "EQ",
        "is_owner": True,
        "information": {"headUnitType": "test"},
    }


def test_oauth_refresh_is_single_and_persists_rotated_token(tmp_path):
    store = TokenStore(tmp_path / "token")
    store.save(
        {
            "region": "North America",
            "token": {"access_token": "old", "refresh_token": "refresh-old", "expires_at": 0},
        }
    )

    async def run():
        auth = Oauth(MagicMock(), "North America", store, MagicMock())
        auth._app_version.async_refresh = AsyncMock()
        auth._get_header = MagicMock(return_value={})
        auth._async_request = AsyncMock(
            side_effect=[
                {},
                {"access_token": "new", "refresh_token": "refresh-new", "expires_in": 3600},
            ]
        )
        tokens = await asyncio.gather(auth.async_get_cached_token(), auth.async_get_cached_token())
        assert all(t["access_token"] == "new" for t in tokens)
        assert auth._async_request.call_count == 2  # preflight plus one refresh

    asyncio.run(run())
    assert TokenStore(store.path).data["token"]["refresh_token"] == "refresh-new"


def test_build_unified_app_does_not_open_cloud_connection(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_SOURCE", "mercedes")
    monkeypatch.setattr(config, "MERCEDES_VIN", VIN)
    monkeypatch.setattr(config, "MERCEDES_REGION", "North America")
    monkeypatch.setattr(config, "MERCEDES_TOKEN_FILE", str(tmp_path / "token"))
    monkeypatch.setattr(config, "CHARGER_ENABLED", True)
    monkeypatch.setattr(config, "HA_MQTT_ENABLED", True)
    monkeypatch.setattr(config, "CERBO_PORTAL_ID", "testportal")
    app = build_app()
    assert app.client._thread is None
    assert app.charger.service.svc["/Connected"] == 0
    assert app.services.ev["/Connected"] == 0
    assert app.mqtt.publish_ha
    app.shutdown()


def test_api_freshness_controls_both_projections_and_mqtt(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MERCEDES_STALE_TIMEOUT", 300)
    monkeypatch.setattr(config, "DATA_SOURCE", "mercedes")
    monkeypatch.setattr(config, "MERCEDES_VIN", VIN)
    monkeypatch.setattr(config, "MERCEDES_TOKEN_FILE", str(tmp_path / "token"))
    monkeypatch.setattr(config, "CHARGER_ENABLED", True)
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr("dbus_ev.main._now", lambda: 1000)
    app = build_app()
    app.mqtt = MagicMock()
    app.apply_snapshot(
        {"ok": True, "soc": 72, "_sample_started_at": 999, "_source_sample_started_at": 600}
    )
    assert app.services.ev["/Connected"] == 0
    assert app.charger.service.svc["/Connected"] == 0
    assert app.mqtt.tick.call_args.args[0]["ok"] is False
    app.apply_snapshot(
        {
            "ok": True,
            "soc": 73,
            "_sample_started_at": 999,
            "_source_sample_started_at": 990,
            "mercedes_charging_status": 3,
            "power": 0,
        }
    )
    assert app.services.ev["/Connected"] == 1
    assert app.charger.service.svc["/Connected"] == 1
    app.apply_snapshot({"ok": False})
    assert app.services.ev["/Connected"] == 0
    assert app.charger.service.svc["/Connected"] == 0


def test_invalid_source_and_vin_fail_before_network(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_SOURCE", "invalid")
    with pytest.raises(ValueError):
        build_app()
    with pytest.raises(ValueError):
        MercedesClient(vin="bad", region="North America", token_file=tmp_path / "token")
    with pytest.raises(ValueError):
        MercedesClient(vin=VIN, region="unknown", token_file=tmp_path / "token")


def test_reconnect_preserves_bounded_freshness_across_outputs(monkeypatch, tmp_path):
    now = [1000.0]
    monkeypatch.setattr("dbus_ev.mercedes.client.time.monotonic", lambda: now[0])
    monkeypatch.setattr("dbus_ev.main._now", lambda: now[0])
    monkeypatch.setattr("dbus_ev.main._write_heartbeat", lambda: None)
    monkeypatch.setattr(config, "DATA_SOURCE", "mercedes")
    monkeypatch.setattr(config, "MERCEDES_VIN", VIN)
    monkeypatch.setattr(config, "MERCEDES_TOKEN_FILE", str(tmp_path / "token"))
    monkeypatch.setattr(config, "CHARGER_ENABLED", True)
    monkeypatch.setattr(config, "CERBO_METER_INSTANCE", None)
    monkeypatch.setattr(config, "MERCEDES_STALE_TIMEOUT", 300)
    app = build_app()
    app.mqtt = MagicMock()
    client = app.client
    client._snapshot = {"soc": 72, "power": 0, "mercedes_charging_status": 3}
    client._received = now[0]
    # Both a short disconnect and a restored socket use the same acquisition age.
    for connected, at, available in [
        (False, 1015, True),
        (True, 1299, True),
        (False, 1300, False),
        (True, 1301, False),
    ]:
        client._connected, now[0] = connected, at
        app.apply_snapshot(client.poll())
        assert bool(app.services.ev["/Connected"]) is available
        assert bool(app.charger.service.svc["/Connected"]) is available
        assert app.mqtt.tick.call_args.args[0]["ok"] is available
        assert client._received == 1000
    now[0] = 1100
    client.close()
    assert not client.poll()["ok"]
