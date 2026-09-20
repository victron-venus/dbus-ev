"""Original mbapi2020 entity presentation (MIT), backed by Cerbo MQTT."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import ATTR_MB_MANUFACTURER, CONF_ENABLE_CHINA_GCJ_02, DOMAIN, LOGGER, UNITS
from .const import SensorConfigFields as scf
from .coordinator import MBAPI2020DataUpdateCoordinator


class MercedesMeEntity(CoordinatorEntity[MBAPI2020DataUpdateCoordinator], Entity):
    """Entity class for MercedesMe devices."""

    _attr_has_entity_name = True

    @property
    def available(self):
        return self._coordinator.available

    def __init__(
        self,
        internal_name: str,
        config: list | EntityDescription,
        vin: str,
        coordinator: MBAPI2020DataUpdateCoordinator,
        should_poll: bool = False,
    ) -> None:
        """Initialize the MercedesMe entity."""

        self._hass = coordinator.hass
        self._coordinator = coordinator
        self._vin = vin
        self._internal_name = internal_name
        self._sensor_config = config
        self._car = self._coordinator.client.cars[self._vin]
        self._feature_name = None
        self._object_name = None
        self._attrib_name = None

        self._flip_result = False
        self._state = None

        # Temporary workaround: If PR get's approved, all entity types should be migrated to the new config classes
        if isinstance(config, EntityDescription):
            self._attributes = config.attributes
            self.entity_description = config
        else:
            self._feature_name = config[scf.OBJECT_NAME.value]
            self._object_name = config[scf.ATTRIBUTE_NAME.value]
            self._attrib_name = config[scf.VALUE_FIELD_NAME.value]
            self._flip_result = config[scf.FLIP_RESULT.value]
            self._attr_device_class = self._sensor_config[scf.DEVICE_CLASS.value]
            self._attr_icon = self._sensor_config[scf.ICON.value]
            self._attr_state_class = self._sensor_config[scf.STATE_CLASS.value]
            self._attr_entity_category = self._sensor_config[scf.ENTITY_CATEGORY.value]
            self._attributes = self._sensor_config[scf.EXTENDED_ATTRIBUTE_LIST.value]
            self._attr_native_unit_of_measurement = self.unit_of_measurement
            self._attr_suggested_display_precision = self._sensor_config[
                scf.SUGGESTED_DISPLAY_PRECISION.value
            ]
            self._use_chinese_location_data: bool = self._coordinator.config_entry.options.get(
                CONF_ENABLE_CHINA_GCJ_02, False
            )
            self._attr_translation_key = self._internal_name.lower()
            self._attr_name = config[scf.DISPLAY_NAME.value]
            self._name = f"{self._car.licenseplate} {config[scf.DISPLAY_NAME.value]}"

        self._attr_device_info = {"identifiers": {(DOMAIN, self._vin)}}
        self._attr_should_poll = should_poll
        self._attr_unique_id = slugify(f"{self._vin}_{self._internal_name}")

        super().__init__(coordinator)

    def device_retrieval_status(self):
        """Return the retrieval_status of the sensor."""
        if self._internal_name == "car":
            return "VALID"

        return self._get_car_value(
            self._feature_name, self._object_name, "retrievalstatus", "error"
        )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""

        state = {"car": self._car.licenseplate, "vin": self._vin}

        if self._attrib_name == "display_value":
            value = self._get_car_value(self._feature_name, self._object_name, "value", None)
            if value:
                state["original_value"] = value

        for item in ["retrievalstatus", "timestamp", "unit"]:
            value = self._get_car_value(self._feature_name, self._object_name, item, None)
            if value:
                state[item] = value if item != "timestamp" else datetime.fromtimestamp(int(value))

        if self._attributes is not None:
            for attrib in sorted(self._attributes):
                if "." in attrib:
                    object_name = attrib.split(".")[0]
                    attrib_name = attrib.split(".")[1]
                else:
                    object_name = self._feature_name
                    attrib_name = attrib
                retrievalstatus = self._get_car_value(
                    object_name, attrib_name, "retrievalstatus", "error"
                )

                if retrievalstatus == "VALID":
                    state[attrib_name] = self._get_car_value(
                        object_name, attrib_name, "display_value", None
                    )
                    if not state[attrib_name]:
                        state[attrib_name] = self._get_car_value(
                            object_name, attrib_name, "value", "error"
                        )

                if retrievalstatus in ["NOT_RECEIVED"]:
                    state[attrib_name] = "NOT_RECEIVED"
        return state

    @property
    def device_info(self) -> DeviceInfo:
        """Device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._vin)},
            manufacturer=ATTR_MB_MANUFACTURER,
            model=self._car.baumuster_description,
            name=self._car.licenseplate,
            sw_version=f"{self._car.vehicle_information.get('headUnitSoftwareVersion', '')} - {self._car.vehicle_information.get('headUnitType', '')}",
            hw_version=f"{self._car.vehicle_information.get('starArchitecture', '')} - {self._car.vehicle_information.get('tcuType', '')}",
        )

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""

        if "unit" in self.extra_state_attributes:
            reported_unit: str = self.extra_state_attributes["unit"]
            if reported_unit.upper() in UNITS:
                return UNITS[reported_unit.upper()]

            LOGGER.warning(
                "Unknown unit %s found. Please report via issue https://www.github.com/renenulschde/mbapi2020/issues",
                reported_unit,
            )
            return reported_unit

        if isinstance(self._sensor_config, EntityDescription):
            return None
        return self._sensor_config[scf.UNIT_OF_MEASUREMENT.value]

    def update(self):
        """Get the latest data and updates the states."""
        if not self.enabled:
            return

        if isinstance(self._sensor_config, EntityDescription):
            self._mercedes_me_update()
        else:
            self._state = self._get_car_value(
                self._feature_name, self._object_name, self._attrib_name, "error"
            )
            self.async_write_ha_state()

    def _mercedes_me_update(self) -> None:
        """Update Mercedes Me entity."""
        raise NotImplementedError

    def _get_car_value(self, feature, object_name, attrib_name, default_value):
        value = None

        if object_name:
            if not feature:
                value = getattr(
                    getattr(self._car, object_name, default_value),
                    attrib_name,
                    default_value,
                )
            else:
                value = getattr(
                    getattr(
                        getattr(self._car, feature, default_value),
                        object_name,
                        default_value,
                    ),
                    attrib_name,
                    default_value,
                )

        else:
            value = getattr(self._car, attrib_name, default_value)

        return value

    def _get_car_attribute(self, feature, object_name):
        """Get the CarAttribute object for this sensor."""
        if object_name:
            if not feature:
                return getattr(self._car, object_name, None)
            feature_obj = getattr(self._car, feature, None)
            if feature_obj:
                return getattr(feature_obj, object_name, None)
        else:
            return getattr(self._car, self._attrib_name, None)

        return None

    def pushdata_update_callback(self):
        """Schedule a state update."""
        self.update()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.update()

    async def async_added_to_hass(self):
        """Add callback after being added to hass.

        Show latest data after startup.
        """
        await super().async_added_to_hass()
        if not self._attr_should_poll:
            self._car.add_update_listener(self.pushdata_update_callback)

        self.async_schedule_update_ha_state(True)
        self._handle_coordinator_update()

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        await super().async_will_remove_from_hass()
        self._car.remove_update_callback(self.pushdata_update_callback)
