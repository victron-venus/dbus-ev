"""Configure an existing Cerbo-to-HA MQTT route; never request Mercedes credentials."""

import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN


def valid_route(data):
    return (
        len(data["vin"]) == 17
        and data["vin"].isascii()
        and data["vin"].isalnum()
        and bool(data["portal_id"])
        and not any(c in data["portal_id"] for c in "/+#\x00")
        and not any(c in data.get("topic_prefix", "") for c in "+#\x00")
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """ConfigFlow implementation."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = dict(user_input, transport="cerbo_mqtt")
            data["vin"] = data["vin"].strip().upper()
            if not valid_route(data):
                errors["base"] = "invalid_config"
            else:
                await self.async_set_unique_id(f"cerbo-{data['portal_id']}-{data['vin']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=data.get("vehicle_name") or data["vin"],
                    data=data,
                    options={"cap_check_disabled": True},
                )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("portal_id"): str,
                    vol.Required("vin"): str,
                    vol.Optional("topic_prefix", default=""): str,
                    vol.Optional("vehicle_name", default="Mercedes-Benz"): str,
                    vol.Optional("stale_timeout", default=900): vol.All(
                        vol.Coerce(int), vol.Range(min=30)
                    ),
                }
            ),
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            data = dict(user_input, transport="cerbo_mqtt")
            data["vin"] = data["vin"].strip().upper()
            if valid_route(data):
                # Replace, rather than merge, so credentials cannot remain in HA storage.
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=data,
                    options={"cap_check_disabled": True},
                    title="Mercedes via Cerbo MQTT",
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")
            errors["base"] = "invalid_config"
        return self.async_show_form(
            step_id="reconfigure",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required("portal_id", default=entry.data.get("portal_id", "")): str,
                    vol.Required("vin", default=entry.data.get("vin", "")): str,
                    vol.Optional("topic_prefix", default=entry.data.get("topic_prefix", "")): str,
                    vol.Optional(
                        "vehicle_name", default=entry.data.get("vehicle_name", "Mercedes-Benz")
                    ): str,
                    vol.Optional(
                        "stale_timeout", default=entry.data.get("stale_timeout", 900)
                    ): vol.All(vol.Coerce(int), vol.Range(min=30)),
                }
            ),
        )
