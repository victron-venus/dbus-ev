"""Common vehicle fields; SI units and unknown values survive every output."""

import math

MQTT_FIELDS = (
    "soc",
    "target_soc",
    "power",
    "battery_capacity",
    "range_to_go",
    "odometer",
    "charging_status",
    "latitude",
    "longitude",
    "at_site",
)


def number(value, minimum=None, maximum=None):
    """Accept finite numbers, including zero, but not booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    if minimum is not None and value < minimum:
        return None
    if maximum is not None and value > maximum:
        return None
    return float(value)


def at_site(snapshot, home):
    """Determine home association from coordinates, never from charging alone."""
    lat, lon, radius = home
    lat = number(lat, -90, 90)
    lon = number(lon, -180, 180)
    radius = number(radius, 0)
    current_lat = number(snapshot.get("latitude"), -90, 90)
    current_lon = number(snapshot.get("longitude"), -180, 180)
    if any(v is None for v in (lat, lon, radius, current_lat, current_lon)):
        return None
    lat1, lat2 = math.radians(lat), math.radians(current_lat)
    dlat = lat2 - lat1
    dlon = math.radians(current_lon - lon)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(max(0, a)))) <= radius


def normalize(data, *, vin, capacity=None, home=(None, None, 150)):
    """Map evcc's A/B/C charge states to Venus enums without inventing readings."""
    state = data.get("status")
    snapshot = {
        "soc": number(data.get("soc"), 0, 100),
        "target_soc": number(data.get("target_soc"), 0, 100),
        "vin": vin,
        "battery_capacity": number(data.get("battery_capacity"), 0) or number(capacity, 0),
        "charging_state": {"A": 0, "B": 0, "C": 3}.get(state),
        "charger_status": {"A": 0, "B": 1, "C": 2}.get(state),
        "charging_status": {"A": "unplugged", "B": "connected", "C": "charging"}.get(state),
        "odometer": number(data.get("odometer"), 0),
        "range_to_go": number(data.get("range_to_go"), 0),
        "latitude": number(data.get("latitude"), -90, 90),
        "longitude": number(data.get("longitude"), -180, 180),
        "power": number(data.get("power")),
    }
    snapshot["at_site"] = at_site(snapshot, home)
    return snapshot
