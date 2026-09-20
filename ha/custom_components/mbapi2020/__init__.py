"""Mercedes telemetry received exclusively through the configured HA MQTT broker."""

from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import MBAPI2020DataUpdateCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.COVER]


async def async_setup_entry(hass, entry):
    if entry.data.get("transport") != "cerbo_mqtt":
        raise ConfigEntryNotReady("Reconfigure this entry for Cerbo MQTT; cloud login is removed")
    coordinator = MBAPI2020DataUpdateCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    try:
        await coordinator.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        coordinator.stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.stop()
        return True
    return False
