# Exercise the internal snapshot ownership boundary without a live connection.
# pylint: disable=protected-access
"""Keep account-wide conversions and raw payload copies out of cached reads."""

import asyncio
import gc
import weakref
from unittest.mock import patch

import aiohttp
import pytest

from dbus_ev.mercedes import protocol as mercedes_protocol
from dbus_ev.mercedes.client import MercedesClient
from dbus_ev.mercedes.protocol import Protocol
from dbus_ev.mercedes.vendor.proto import client_pb2, vehicle_events_pb2

VIN = "WDD00000000000001"
OTHER_VIN = "WDD00000000000002"


@pytest.mark.parametrize("legacy", [False, True])
def test_decode_converts_only_the_selected_vehicle(legacy):
    message = vehicle_events_pb2.PushMessage()
    if legacy:
        cars = message.vepUpdates.updates
        for vin in (VIN, OTHER_VIN):
            cars[vin].vin = vin
            cars[vin].attributes["soc"].int_value = 60
    else:
        cars = message.vehicle_status_updates.vehicle_status_updates
        for vin in (VIN, OTHER_VIN):
            cars[vin].fin_or_vin = vin
            cars[vin].soc.value = 60

    with patch.object(
        mercedes_protocol, "MessageToDict", wraps=mercedes_protocol.MessageToDict
    ) as convert:
        _, snapshot = Protocol(VIN).decode(message.SerializeToString())
    assert isinstance(snapshot, dict)
    # Pylint cannot infer protobuf's generated oneof/map behavior in decode().
    assert snapshot["vin"] == VIN  # pylint: disable=unsubscriptable-object
    assert convert.call_count == 1
    converted_car = convert.call_args.args[0]
    assert (converted_car.vin if legacy else converted_car.fin_or_vin) == VIN


@pytest.mark.parametrize("legacy", [False, True])
def test_other_vehicle_is_acknowledged_without_conversion(legacy):
    message = vehicle_events_pb2.PushMessage()
    if legacy:
        message.vepUpdates.sequence_number = 23
        message.vepUpdates.updates[OTHER_VIN].attributes["soc"].int_value = 60
        acknowledgement = "acknowledge_vep_updates_by_vin"
    else:
        message.vehicle_status_updates.sequence_number = 23
        message.vehicle_status_updates.vehicle_status_updates[OTHER_VIN].soc.value = 60
        acknowledgement = "acknowledge_vehicle_status_updates"

    with patch("dbus_ev.mercedes.protocol.MessageToDict") as convert:
        ack, snapshot = Protocol(VIN).decode(message.SerializeToString())
    assert snapshot is None
    assert getattr(client_pb2.ClientMessage.FromString(ack), acknowledgement).sequence_number == 23
    convert.assert_not_called()


def test_account_event_is_acknowledged_without_conversion():
    message = vehicle_events_pb2.PushMessage()
    message.service_status_updates.sequence_number = 24
    with patch("dbus_ev.mercedes.protocol.MessageToDict") as convert:
        ack, snapshot = Protocol(VIN).decode(message.SerializeToString())
    assert snapshot is None
    assert (
        client_pb2.ClientMessage.FromString(ack).acknowledge_service_status_update.sequence_number
        == 24
    )
    convert.assert_not_called()


def test_cached_snapshot_keeps_published_payload_stable_across_updates(tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    protocol = Protocol(VIN)
    first = protocol.merge({"attributes": {"soc": {"value": 50, "timestamp_in_ms": 100}}})
    client._accept(first, "push")

    borrowed = client.cached_snapshot()
    assert client.cached_snapshot()["mercedes_payload"] is borrowed["mercedes_payload"]
    borrowed["soc"] = 99
    assert client.cached_snapshot()["soc"] == 50

    second = protocol.merge({"attributes": {"soc": {"value": 51, "timestamp_in_ms": 200}}})
    client._accept(second, "push")
    latest = client.cached_snapshot()
    assert latest["soc"] == 51
    assert latest["mercedes_payload"] is not borrowed["mercedes_payload"]
    assert borrowed["mercedes_payload"]["attributes"]["soc"]["value"] == 50

    independent = client.poll()
    independent["mercedes_payload"]["attributes"]["soc"]["value"] = 1
    assert latest["mercedes_payload"]["attributes"]["soc"]["value"] == 51
    assert client.poll()["mercedes_payload"]["attributes"]["soc"]["value"] == 51


def test_quiet_stream_releases_completed_frame_and_obsolete_payload(tmp_path):
    client = MercedesClient(vin=VIN, region="North America", token_file=tmp_path / "token")
    references = {}

    class Frame:
        """A weak-referenceable stand-in for the WebSocket's binary message."""

        type = aiohttp.WSMsgType.BINARY
        data = b"synthetic protobuf frame"

    class Payload(dict):
        """Track when a decoded payload stops being retained by the stream."""

    class Decoder:
        """Provide one payload without retaining the raw message."""

        def decode(self, raw):
            assert raw == Frame.data
            payload = Payload(vin=VIN, attributes={"soc": {"value": 50}})
            references["payload"] = weakref.ref(payload)
            return b"ack", payload

    async def scenario():
        waiting = asyncio.Event()

        class Socket:
            """Yield one frame and keep the next receive pending."""

            first = True

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.first:
                    self.first = False
                    frame = Frame()
                    references["frame"] = weakref.ref(frame)
                    references["task"] = weakref.ref(asyncio.current_task())
                    return frame
                waiting.set()
                await asyncio.Future()

            async def send_bytes(self, ack):
                assert ack == b"ack"

        client._next_pull = float("inf")
        stream = asyncio.create_task(client._stream(Socket(), None, None, None, Decoder()))
        try:
            await asyncio.wait_for(waiting.wait(), timeout=1)
            gc.collect()
            assert references["frame"]() is None
            assert references["task"]() is None
            assert references["payload"]() is client._payload

            # A REST acquisition can replace the cached payload while the reader
            # is still waiting. The stream must not keep the old push payload.
            client._accept({"vin": VIN, "attributes": {"soc": {"value": 51}}}, "pull")
            gc.collect()
            assert references["payload"]() is None
            assert client.poll()["soc"] == 51
        finally:
            stream.cancel()
            await asyncio.gather(stream, return_exceptions=True)

    asyncio.run(scenario())
