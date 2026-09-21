# Exercise network/cache boundaries without real credentials or commands.
# pylint: disable=protected-access
"""REST fallback, rate limits, partial replies and recovery regressions."""

import asyncio
from email.utils import formatdate
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from dbus_ev.mercedes.client import MercedesClient, retry_delay, vehicle_snapshot
from dbus_ev.mercedes.protocol import Protocol
from dbus_ev.mercedes.vendor.proto import vehicle_events_pb2
from tests.test_mercedes_lifecycle import Context

VIN = "WDD00000000000001"


def rest_frame(vin=VIN, *, legacy=False):
    if legacy:
        frame = vehicle_events_pb2.VEPUpdate()
        frame.vin = vin
        frame.attributes["soc"].int_value = 81
    else:
        frame = vehicle_events_pb2.VehicleStatusUpdate()
        frame.fin_or_vin = vin
        frame.soc.value = 81
        frame.soc.metadata.timestamp.seconds = 100
    return frame.SerializeToString()


@pytest.mark.parametrize("legacy", [False, True])
def test_rest_schema_and_vin_validation(legacy):
    protocol = Protocol(VIN)
    snapshot = protocol.decode_rest(rest_frame(legacy=legacy))
    assert vehicle_snapshot(snapshot)["soc"] == 81
    assert snapshot["full_update"]
    assert protocol.decode_rest(rest_frame("WDD00000000000002", legacy=legacy)) is None
    assert protocol.decode_rest(b"") is None


def test_partial_rest_does_not_revalidate_old_push_charging_values():
    protocol = Protocol(VIN)
    push = vehicle_events_pb2.PushMessage()
    car = push.vepUpdates.updates[VIN]
    car.vin = VIN
    car.attributes["soc"].int_value = 70
    car.attributes["chargingPower"].double_value = 7.2
    protocol.decode(push.SerializeToString())
    snapshot = protocol.decode_rest(rest_frame())
    assert vehicle_snapshot(snapshot)["power"] is None
    assert "chargingPower" not in snapshot["attributes"]
    # The separate push merge buffer still accepts subsequent stream deltas.
    assert "chargingPower" in protocol.attributes


def test_pull_refreshes_snapshot_without_a_websocket_and_then_expires(monkeypatch, tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    session, response, versions, auth = (MagicMock() for _ in range(4))
    response.read = AsyncMock(return_value=rest_frame())
    session.get.return_value = Context(response)
    versions.async_refresh = AsyncMock()
    versions.apply_webapi_headers.side_effect = lambda headers: headers
    auth.async_get_cached_token = AsyncMock(return_value={"access_token": "private"})
    asyncio.run(client._pull(session, auth, versions, Protocol(VIN)))
    snapshot = client.poll()
    assert snapshot["ok"] and snapshot["soc"] == 81
    assert snapshot["mercedes_payload"]["data_mode"] == "pull"
    assert not client._connected
    acquired = client._received
    assert 179 <= client._pull_delay() <= 180
    # A successful HTTP reply without vehicle data must never renew availability.
    response.read.return_value = b""
    asyncio.run(client._pull(session, auth, versions, Protocol(VIN)))
    assert client._received == acquired
    monkeypatch.setattr("dbus_ev.mercedes.client.time.monotonic", lambda: acquired + 301)
    assert not client.poll()["ok"]
    auth.async_login_new.assert_not_called()


def test_pull_honors_rate_limit_without_renewing_data(tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    session, response, versions, auth = (MagicMock() for _ in range(4))
    response.raise_for_status.side_effect = aiohttp.ClientResponseError(
        None, (), status=429, headers={"Retry-After": "3600"}
    )
    session.get.return_value = Context(response)
    versions.async_refresh = AsyncMock()
    auth.async_get_cached_token = AsyncMock(return_value={"access_token": "private"})
    asyncio.run(client._pull(session, auth, versions, Protocol(VIN)))
    assert 3599 <= client._pull_delay() <= 3600
    assert client._received is None
    assert not client.poll()["ok"]


@pytest.mark.parametrize("header", [None, "nonsense", "nan", "-20", "15"])
def test_retry_after_cannot_shorten_backoff(header):
    assert retry_delay(SimpleNamespace(headers={"Retry-After": header}), 900) == 900


def test_retry_after_accepts_seconds_and_http_date(monkeypatch):
    monkeypatch.setattr("dbus_ev.mercedes.client.time.time", lambda: 1000)
    for header in ["3600", formatdate(4600, usegmt=True)]:
        assert retry_delay(SimpleNamespace(headers={"Retry-After": header}), 900) == 3600


def test_rate_limited_websocket_keeps_rest_running_and_recovers(monkeypatch, tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    session, versions, auth = (MagicMock() for _ in range(3))
    versions.async_refresh = AsyncMock()
    versions.apply_websocket_headers.side_effect = lambda headers: headers
    auth.async_get_cached_token = AsyncMock(return_value={"access_token": "private"})
    limited = aiohttp.WSServerHandshakeError(None, (), status=429, headers={"Retry-After": "1200"})
    session.ws_connect.side_effect = [limited, Context(MagicMock())]
    monkeypatch.setattr(
        "dbus_ev.mercedes.client.aiohttp.ClientSession", lambda **_: Context(session)
    )
    monkeypatch.setattr("dbus_ev.mercedes.client.AppVersionManager", lambda _: versions)
    monkeypatch.setattr("dbus_ev.mercedes.client.Oauth", lambda *_: auth)
    metadata = AsyncMock(return_value={})
    monkeypatch.setattr(client, "_metadata", metadata)
    cooldowns = []

    async def cooldown(s, a, v, protocol, delay):
        assert s is session and a is auth and v is versions
        cooldowns.append(delay)
        if len(cooldowns) == 1:
            client._accept(protocol.decode_rest(rest_frame()), "pull")
            assert client.poll()["ok"]
        else:
            client._stop.set()

    async def stream(*_args):
        assert client._connected
        frame = vehicle_events_pb2.PushMessage()
        frame.vepUpdates.updates[VIN].attributes["soc"].int_value = 82
        client._accept(Protocol(VIN).decode(frame.SerializeToString())[1], "push")
        assert client.poll()["soc"] == 82
        assert client.poll()["mercedes_payload"]["data_mode"] == "push"

    monkeypatch.setattr(client, "_cooldown", cooldown)
    monkeypatch.setattr(client, "_stream", stream)
    asyncio.run(client._serve())
    assert cooldowns == [1200, 15]
    assert session.ws_connect.call_count == 2
    headers = [call.kwargs["headers"] for call in session.ws_connect.call_args_list]
    assert headers[0]["APP-SESSION-ID"] == headers[1]["APP-SESSION-ID"]
    metadata.assert_awaited_once()
    auth.async_login_new.assert_not_called()


def test_cooldown_runs_three_minute_polls_without_busy_loop(monkeypatch, tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    now, polls = [1000.0], []
    monkeypatch.setattr("dbus_ev.mercedes.client.time.monotonic", lambda: now[0])

    async def sleep(delay):
        assert delay > 0
        now[0] += delay

    async def pull(*_args):
        polls.append(now[0])
        client._next_pull = now[0] + 180

    monkeypatch.setattr("dbus_ev.mercedes.client.asyncio.sleep", sleep)
    monkeypatch.setattr(client, "_pull", pull)
    asyncio.run(client._cooldown(None, None, None, None, 900))
    assert polls == [1000, 1180, 1360, 1540, 1720]
    assert now[0] == 1900
