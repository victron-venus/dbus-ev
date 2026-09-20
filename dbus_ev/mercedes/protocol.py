"""Decode Mercedes push frames and retain complete, ordered vehicle snapshots."""

import copy
import math
import time

from google.protobuf.json_format import MessageToDict

from .vendor.proto import client_pb2, vehicle_events_pb2
from .vendor.vsu_helper import normalize_vsu_car

ACKS = {
    "vepUpdates": "acknowledge_vep_updates_by_vin",
    "vehicle_status_updates": "acknowledge_vehicle_status_updates",
    "service_status_updates": "acknowledge_service_status_update",
    "user_data_update": "acknowledge_user_data_update",
    "user_picture_update": "acknowledge_user_picture_update",
    "user_pin_update": "acknowledge_user_pin_update",
    "vehicle_updated": "acknowledge_vehicle_updated",
    "preferred_dealer_change": "acknowledge_preferred_dealer_change",
    "apptwin_command_status_updates_by_vin": "acknowledge_apptwin_command_status_update_by_vin",
    "data_change_event": "acknowledge_data_change_event",
}


def finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


class Protocol:
    """Decode push messages, acknowledge events and merge vehicle updates."""

    def __init__(self, vin):
        self.vin = vin
        self.attributes = {}
        self.full_received = False
        self.revision = 0

    def decode(self, raw):
        message = vehicle_events_pb2.PushMessage()
        message.ParseFromString(raw)
        kind = message.WhichOneof("msg")
        reply = None
        if kind in ACKS:
            ack = client_pb2.ClientMessage()
            getattr(ack, ACKS[kind]).sequence_number = getattr(message, kind).sequence_number
            reply = ack.SerializeToString()
        elif kind == "assigned_vehicles":
            reply = bytes.fromhex("ba0100")
        elif kind == "apptwin_pending_command_request":
            reply = bytes.fromhex("aa0100")
        data = MessageToDict(message, preserving_proto_field_name=True)
        updates = {}
        if kind == "vepUpdates":
            updates = data.get(kind, {}).get("updates", {})
        elif kind == "vehicle_status_updates":
            updates = {
                vin: normalize_vsu_car(car) for vin, car in data.get(kind, {}).get(kind, {}).items()
            }
        update = updates.get(self.vin)
        return reply, self.merge(update) if update else None

    def merge(self, update):
        incoming = update.get("attributes")
        if not isinstance(incoming, dict) or not incoming:
            return None
        if update.get("full_update"):
            self.attributes = {}
            self.full_received = True
        for key, value in incoming.items():
            if not isinstance(value, dict):
                continue
            old = self.attributes.get(key, {})
            old_time = finite(old.get("timestamp_in_ms", 0)) or 0
            new_time = finite(value.get("timestamp_in_ms", 0)) or 0
            if new_time >= old_time:
                self.attributes[key] = copy.deepcopy(value)
        self.revision += 1
        return {
            "schema": 1,
            "vin": self.vin,
            "revision": self.revision,
            "received_at": time.time(),
            "full_update": self.full_received,
            "attributes": copy.deepcopy(self.attributes),
        }
