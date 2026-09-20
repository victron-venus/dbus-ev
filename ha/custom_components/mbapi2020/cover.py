"""Read-only window positions using the original mbapi2020 unique IDs and enums."""

from homeassistant.components.cover import CoverDeviceClass, CoverEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN

WINDOWS = {
    "windows": "windowStatusOverall",
    "window_front_left": "windowstatusfrontleft",
    "window_front_right": "windowstatusfrontright",
    "window_rear_left": "windowstatusrearleft",
    "window_rear_right": "windowstatusrearright",
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([Window(coordinator, key, field) for key, field in WINDOWS.items()])


class Window(CoordinatorEntity, CoverEntity):
    """Window implementation."""

    _attr_has_entity_name = True
    _attr_device_class = CoverDeviceClass.WINDOW
    _attr_supported_features = 0

    def __init__(self, coordinator, key, field):
        super().__init__(coordinator)
        self.key, self.field = key, field
        self._attr_unique_id = slugify(f"{coordinator.vin}_{key}")
        self._attr_translation_key = key
        self._attr_device_info = {"identifiers": {(DOMAIN, coordinator.vin)}}

    @property
    def available(self):
        return self.coordinator.available

    @property
    def current_cover_position(self):
        car = self.coordinator.client.cars[self.coordinator.vin]
        attr = getattr(car.windows, self.field, None)
        if attr is None or str(attr.retrievalstatus) != "VALID":
            return None
        status = attr.value
        if isinstance(status, bool):
            return 0 if status else 100
        if status in ("OPEN", "CLOSED"):
            return 100 if status == "OPEN" else 0
        try:
            positions = (
                {0: 50, 1: 0, 2: 100, 3: 10}
                if self.key == "windows"
                else {
                    0: 50,
                    1: 100,
                    2: 0,
                    3: 10,
                    4: 50,
                }
            )
            return positions.get(int(status))
        except (TypeError, ValueError):
            return None

    @property
    def is_closed(self):
        position = self.current_cover_position
        return None if position is None else position == 0
