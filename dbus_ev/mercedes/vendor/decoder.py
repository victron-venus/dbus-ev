"""Telemetry-only value decoder extracted from mbapi2020 client.py (MIT)."""

from __future__ import annotations

import datetime as dt
import logging
import time
import traceback
from datetime import datetime
from typing import Any

from .car import (
    AUX_HEAT_OPTIONS,
    BINARY_SENSOR_OPTIONS,
    DOOR_OPTIONS,
    ELECTRIC_OPTIONS,
    LOCATION_OPTIONS,
    ODOMETER_OPTIONS,
    PRE_COND_OPTIONS,
    TIRE_OPTIONS,
    WINDOW_OPTIONS,
    WIPER_OPTIONS,
    Auxheat,
    BinarySensors,
    Car,
    CarAlarm,
    CarAlarm_OPTIONS,
    CarAttribute,
    Doors,
    Electric,
    Location,
    Odometer,
    Precond,
    Tires,
    Windows,
    Wipers,
)
from .helper import LogHelper as loghelper

STATE_UNKNOWN = "unknown"
LOGGER = logging.getLogger(__name__)


class Decoder:
    def __init__(self):
        self.cars = {}
        self.ignition_states = {}
        self.excluded_cars = []

    def _build_car(self, received_car_data, update_mode, is_rest_data=False):
        if received_car_data.get("vin") in self.excluded_cars:
            LOGGER.debug("CAR excluded: %s", loghelper.Mask_VIN(received_car_data.get("vin")))
            return

        if received_car_data.get("vin") not in self.cars:
            LOGGER.info(
                "Flow Problem - VepUpdate for unknown car: %s",
                loghelper.Mask_VIN(received_car_data.get("vin")),
            )

            current_car = Car(received_car_data.get("vin"))
            current_car.licenseplate = received_car_data.get("vin")
            self.cars[received_car_data.get("vin")] = current_car

        car: Car = self.cars.get(received_car_data.get("vin"), Car(received_car_data.get("vin")))

        car.messages_received.update("p" if update_mode else "f")
        car.last_message_received = int(round(time.time() * 1000))

        if not update_mode:
            car.last_full_message = received_car_data

        # Set data collection mode based on data source
        if is_rest_data:
            car.data_collection_mode = "pull"
        else:
            car.data_collection_mode = "push"

        # For REST data, create synthetic windowStatusOverall if missing
        if is_rest_data and received_car_data.get("attributes"):
            if "windowStatusOverall" not in received_car_data["attributes"]:
                self._create_synthetic_window_status_overall(received_car_data, car.finorvin)

        car.odometer = self._get_car_values(
            received_car_data,
            car.finorvin,
            Odometer() if not car.odometer else car.odometer,
            ODOMETER_OPTIONS,
            update_mode,
        )

        car.tires = self._get_car_values(
            received_car_data,
            car.finorvin,
            Tires() if not car.tires else car.tires,
            TIRE_OPTIONS,
            update_mode,
        )

        car.wipers = self._get_car_values(
            received_car_data,
            car.finorvin,
            Wipers() if not car.wipers else car.wipers,
            WIPER_OPTIONS,
            update_mode,
        )

        car.doors = self._get_car_values(
            received_car_data,
            car.finorvin,
            Doors() if not car.doors else car.doors,
            DOOR_OPTIONS,
            update_mode,
        )

        car.location = self._get_car_values(
            received_car_data,
            car.finorvin,
            Location() if not car.location else car.location,
            LOCATION_OPTIONS,
            update_mode,
        )

        car.binarysensors = self._get_car_values(
            received_car_data,
            car.finorvin,
            BinarySensors() if not car.binarysensors else car.binarysensors,
            BINARY_SENSOR_OPTIONS,
            update_mode,
        )

        car.windows = self._get_car_values(
            received_car_data,
            car.finorvin,
            Windows() if not car.windows else car.windows,
            WINDOW_OPTIONS,
            update_mode,
        )

        car.electric = self._get_car_values(
            received_car_data,
            car.finorvin,
            Electric() if not car.electric else car.electric,
            ELECTRIC_OPTIONS,
            update_mode,
        )

        car.auxheat = self._get_car_values(
            received_car_data,
            car.finorvin,
            Auxheat() if not car.auxheat else car.auxheat,
            AUX_HEAT_OPTIONS,
            update_mode,
        )

        car.precond = self._get_car_values(
            received_car_data,
            car.finorvin,
            Precond() if not car.precond else car.precond,
            PRE_COND_OPTIONS,
            update_mode,
        )

        car.caralarm = self._get_car_values(
            received_car_data,
            car.finorvin,
            CarAlarm() if not car.caralarm else car.caralarm,
            CarAlarm_OPTIONS,
            update_mode,
        )

        if not update_mode:
            car.entry_setup_complete = True

        self.cars[car.finorvin] = car

    def _get_car_values(self, car_detail, vin, class_instance, options, update):
        # Define handlers for specific options and the generic case
        option_handlers = {
            "max_soc": self._get_car_values_handle_max_soc,
            "chargeflap": self._get_car_values_handle_chargeflap,
            "chargeinletcoupler": self._get_car_values_handle_chargeinletcoupler,
            "chargeinletlock": self._get_car_values_handle_chargeinletlock,
            "chargePrograms": self._get_car_values_handle_chargePrograms,
            "chargingBreakClockTimer": self._get_car_values_handle_charging_break_clock_timer,
            "chargingPowerRestriction": self._get_car_values_handle_charging_power_restriction,
            "endofchargetime": self._get_car_values_handle_endofchargetime,
            "ignitionstate": self._get_car_values_handle_ignitionstate,
            "precondStatus": self._get_car_values_handle_precond_status,
            "temperature_points_frontLeft": self._get_car_values_handle_temperature_points,
            "temperature_points_frontRight": self._get_car_values_handle_temperature_points,
            "temperature_points_rearLeft": self._get_car_values_handle_temperature_points,
            "temperature_points_rearRight": self._get_car_values_handle_temperature_points,
        }

        if car_detail is None or not car_detail.get("attributes"):
            LOGGER.debug(
                "get_car_values %s has incomplete update data – attributes not found",
                loghelper.Mask_VIN(vin),
            )
            return class_instance

        for option in options:
            # Select the specific handler or the generic handler
            handler = option_handlers.get(option, self._get_car_values_handle_generic)

            curr_status = handler(car_detail, class_instance, option, update, vin)
            if curr_status is None:
                continue

            # Set the value only if the timestamp is newer
            # curr_timestamp = float(curr_status.timestamp or 0)
            # car_value_timestamp = float(self._get_car_value(class_instance, option, "ts", 0))
            # if curr_timestamp > car_value_timestamp:
            #     setattr(class_instance, option, curr_status)
            # elif curr_timestamp < car_value_timestamp:
            #     LOGGER.warning(
            #         "get_car_values %s received older attribute data for %s. Ignoring value.",
            #         loghelper.Mask_VIN(vin),
            #         option,
            #     )
            setattr(class_instance, option, curr_status)
        return class_instance

    def _get_car_values_handle_generic(self, car_detail, class_instance, option, update, vin: str):
        curr = car_detail.get("attributes", {}).get(option)
        if curr:
            # Simplify value extraction by checking for existing keys
            value = next(
                (
                    curr[key]
                    for key in ("value", "int_value", "double_value", "bool_value")
                    if key in curr
                ),
                0,
            )
            status = curr.get("status", "VALID")
            time_stamp = curr.get("timestamp", 0)
            curr_display_value = curr.get("display_value")

            unit_keys = [
                "distance_unit",
                "ratio_unit",
                "clock_hour_unit",
                "gas_consumption_unit",
                "pressure_unit",
                "electricity_consumption_unit",
                "combustion_consumption_unit",
                "speed_unit",
            ]
            unit = next((curr[key] for key in unit_keys if key in curr), None)

            return CarAttribute(
                value=value,
                retrievalstatus=status,
                timestamp=time_stamp,
                display_value=curr_display_value,
                unit=unit,
            )

        if not update:
            # Set status for non-existing values when no update occurs
            return CarAttribute(0, 4, 0)

        return None

    def _get_car_values_handle_max_soc(
        self,
        car_detail,
        class_instance,
        option,
        update,
        vin: str,
        use_last_full_message: bool = False,
    ):
        # Handle the case when the selected charge program changed but chargePrograms is not available in the update message.
        if not use_last_full_message:
            attributes = car_detail.get("attributes", {})
            charge_programs = attributes.get("chargePrograms")
            if not charge_programs:
                if not attributes.get("selectedChargeProgram"):
                    return None

                return self._get_car_values_handle_max_soc(
                    car_detail, class_instance, option, update, vin, use_last_full_message=True
                )
        else:
            current_car = self.cars.get(vin)
            if not current_car or not current_car.last_full_message:
                LOGGER.debug(
                    "get_car_values_handle_max_soc - No last_full_message found for car %s",
                    loghelper.Mask_VIN(vin),
                )
                return None
            car_detail = current_car.last_full_message or car_detail
            attributes = car_detail.get("attributes", {})
            charge_programs = attributes.get("chargePrograms")
            if not charge_programs:
                return None

        time_stamp = charge_programs.get("timestamp", 0)
        charge_programs_value = charge_programs.get("charge_programs_value", {})
        charge_program_parameters = charge_programs_value.get("charge_program_parameters", [])

        selected_program_index = int(
            self._get_car_value(class_instance, "selectedChargeProgram", "value", 0)
        )

        # Ensure the selected index is within bounds
        if 0 <= selected_program_index < len(charge_program_parameters):
            program_parameters = charge_program_parameters[selected_program_index]
            max_soc = program_parameters.get("max_soc")
            if max_soc is not None:
                return CarAttribute(
                    value=max_soc,
                    retrievalstatus="VALID",
                    timestamp=time_stamp,
                    display_value=max_soc,
                    unit="PERCENT",
                )

        return None

    def _get_car_values_handle_chargeflap(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargeFlaps")
        if not curr:
            return None

        charge_flaps_value = curr.get("charge_flaps", {})
        values = charge_flaps_value.get("entries", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        value = values[0].get("position_state", None)

        if value is None:
            return None

        if value == "CHARGE_FLAPS_POSITION_STATE_OPEN":
            value = "open"
        elif value == "CHARGE_FLAPS_POSITION_STATE_CLOSED":
            value = "closed"
        elif value == "CHARGE_FLAPS_POSITION_STATE_FLAP_PRESSED":
            value = "pressed"
        elif value == "CHARGE_FLAPS_POSITION_STATE_UNKNOWN":
            value = STATE_UNKNOWN
        else:
            value = STATE_UNKNOWN
            LOGGER.debug(
                "Unknown chargeFlaps position_state value: %s. Please report this value via an github issue.",
                value,
            )

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_chargeinletcoupler(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargeInlets")
        if not curr:
            return None

        values = curr.get("charge_inlets", {}).get("entries", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        value = values[0].get("coupler_state", None)

        if value is None:
            return None

        if value == "CHARGE_INLETS_COUPLER_STATE_PLUGGED":
            value = "plugged"
        elif value == "CHARGE_INLETS_COUPLER_STATE_VEHICLE_PLUGGED":
            value = "vehicle plugged"
        elif value == "CHARGE_INLETS_COUPLER_STATE_VEHICLE_NOT_PLUGGED":
            value = "vehicle not plugged"
        elif value == "CHARGE_INLETS_COUPLER_STATE_DEFECT":
            value = "defect"
        elif value == "CHARGE_INLETS_COUPLER_STATE_UNKNOWN":
            value = STATE_UNKNOWN
        else:
            value = STATE_UNKNOWN
            LOGGER.debug(
                "Unknown chargeInlets coupler_state value: %s. Please report this value via an github issue.",
                value,
            )

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_chargeinletlock(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargeInlets")
        if not curr:
            return None

        values = curr.get("charge_inlets", {}).get("entries", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        value = values[0].get("lock_state", None)

        if value is None:
            return None

        if value == "CHARGE_INLETS_LOCK_STATE_UNLOCKED":
            value = "unlocked"
        elif value == "CHARGE_INLETS_LOCK_STATE_LOCKED":
            value = "locked"
        elif value == "CHARGE_INLETS_LOCK_STATE_LOCK_STATE_NOT_CLEAR":
            value = "state not clear"
        elif value == "CHARGE_INLETS_LOCK_STATE_NOT_AVAILABLE":
            value = "state not available"
        elif value == "CHARGE_INLETS_LOCK_STATE_UNKNOWN":
            value = STATE_UNKNOWN
        else:
            value = STATE_UNKNOWN
            LOGGER.debug(
                "Unknown chargeInlets lock_state value: %s. Please report this value via an github issue.",
                value,
            )

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_chargePrograms(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get(option)
        if not curr:
            return None

        charge_programs_value = curr.get("charge_programs_value", {})
        value = charge_programs_value.get("charge_program_parameters", [])
        if not value:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_charging_power_restriction(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get("chargingPowerRestriction")
        if not curr:
            return None

        charge_flaps_value = curr.get("charging_power_restrictions", {})
        values = charge_flaps_value.get("charging_power_restriction", [])
        if not values:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)

        if len(values) == 0:
            return None

        value = ", ".join(item.replace("CHARGING_POWER_RESTRICTION_", "") for item in values)

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=None,
            unit=None,
        )

    def _get_car_values_handle_endofchargetime(
        self, car_detail, class_instance, option, update, vin: str
    ):
        # Beginning with CLA 2025 charge end time is part of chargingPredictionMaxSoc

        attributes = car_detail.get("attributes", {})

        chargingPredictionMaxSoc = attributes.get("chargingPredictionMaxSoc", {})
        charging_prediction_soc = chargingPredictionMaxSoc.get("charging_prediction_soc", {})
        predicted_end_time = charging_prediction_soc.get("predicted_end_time", None)
        if predicted_end_time is not None:
            status = chargingPredictionMaxSoc.get("status", "VALID")
            time_stamp = chargingPredictionMaxSoc.get("timestamp", 0)

            if isinstance(predicted_end_time, datetime):
                value = predicted_end_time
            elif isinstance(predicted_end_time, str):
                try:
                    value = datetime.strptime(predicted_end_time, "%Y-%m-%dT%H:%M:%SZ").replace(
                        tzinfo=dt.UTC
                    )
                except Exception:
                    value = None
            else:
                value = None
            if value is not None:
                return CarAttribute(
                    value=value,
                    retrievalstatus=status,
                    timestamp=time_stamp,
                    display_value=value,
                    unit=None,
                )

        # if chargingPredictionMaxSoc is not available and update is false (not a full_message), we want to check if the car is >= CLA2025 and create the data structure with value unknown
        # endofchargetime is not present for these cars
        if not update and not predicted_end_time:
            current_car = self.cars.get(vin)
            if not attributes.get("endofchargetime") and not (
                current_car
                and current_car.last_full_message
                and current_car.last_full_message.get("attributes", {}).get("endofchargetime")
            ):
                return CarAttribute(
                    value=STATE_UNKNOWN,
                    retrievalstatus="VALID",
                    timestamp=datetime.now().timestamp(),
                    display_value=STATE_UNKNOWN,
                    unit=None,
                )

        # Older cars have two attributes endofchargetime and endofChargeTimeWeekday
        # endofchargetime is in minutes after midnight
        try:
            endofchargetime = attributes.get("endofchargetime", {})
            if not endofchargetime:
                return None
            time_stamp = endofchargetime.get("timestamp", 0)
            end_time_value = endofchargetime.get("int_value", None)
            status = endofchargetime.get("status", "VALID")
            if end_time_value is None and status == 3:
                return CarAttribute(
                    value=STATE_UNKNOWN,
                    retrievalstatus=status,
                    timestamp=time_stamp,
                    display_value=STATE_UNKNOWN,
                    unit=None,
                )

            if end_time_value is None:
                LOGGER.warning(
                    "get_car_values_handle_endofchargetime - endofChargeTime value is None for car %s",
                    loghelper.Mask_VIN(vin),
                )
                return None

            # endofChargeTimeWeekday is sometimes not present in the update message, we need to get it from the last full message then
            if "endofChargeTimeWeekday" not in attributes:
                current_car = self.cars.get(vin)
                if not current_car or not current_car.last_full_message:
                    LOGGER.debug(
                        "get_car_values_handle_endofchargetime - No last_full_message found for car %s",
                        loghelper.Mask_VIN(vin),
                    )
                    return None
                car_detail = current_car.last_full_message
                attributes = car_detail.get("attributes", {})

            local_tz = dt.datetime.now().astimezone().tzinfo
            end_weekday_attr = attributes.get("endofChargeTimeWeekday", {})
            end_weekday_value = end_weekday_attr.get("int_value", None)
            if end_weekday_value is None:
                # Wenn kein Wochentag vorhanden ist (sehr alte elek. modelle), aus end_time_value ableiten:
                # Ist die Uhrzeit bereits vergangen -> Wochentag von morgen, sonst von heute.
                now = dt.datetime.now(local_tz)
                hour = int(end_time_value) // 60
                minute = int(end_time_value) % 60
                target_dt_today = dt.datetime(
                    now.year, now.month, now.day, hour, minute, tzinfo=local_tz
                )
                if target_dt_today < now:
                    end_weekday_value = (now + dt.timedelta(days=1)).weekday()
                else:
                    end_weekday_value = now.weekday()

            # Calculate the next occurrence of the given weekday and time in local timezone
            now = dt.datetime.now(local_tz)
            # Python's weekday: Monday=0
            target_weekday = float(end_weekday_value) % 7
            # Calculate days until next target_weekday
            days_ahead = (target_weekday - now.weekday()) % 7

            target_date = now + dt.timedelta(days=days_ahead)
            hour = int(end_time_value) // 60
            minute = int(end_time_value) % 60
            dt_with_time = dt.datetime(
                target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=local_tz
            )

            return CarAttribute(
                value=dt_with_time,
                retrievalstatus=status,
                timestamp=time_stamp,
                display_value=dt_with_time.isoformat(),
                unit=None,
            )
        except Exception as e:
            LOGGER.error(
                "Error processing endofchargetime for car %s: %s, %s",
                loghelper.Mask_VIN(vin),
                e,
                traceback.format_exc(),
            )
            return None

    def _get_car_values_handle_charging_break_clock_timer(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})
        curr = attributes.get(option)
        if not curr:
            return None

        charging_timer_value = curr.get("chargingbreak_clocktimer_value", {})
        value = charging_timer_value.get("chargingbreak_clocktimer_entry")
        if value is None:
            return None

        status = curr.get("status", "VALID")
        time_stamp = curr.get("timestamp", 0)
        curr_display_value = curr.get("display_value")

        return CarAttribute(
            value=value,
            retrievalstatus=status,
            timestamp=time_stamp,
            display_value=curr_display_value,
            unit=None,
        )

    def _get_car_values_handle_ignitionstate(
        self, car_detail, class_instance, option, update, vin: str
    ):
        value = self._get_car_values_handle_generic(car_detail, class_instance, option, update, vin)
        if value:
            vin = car_detail.get("vin")
            self.ignition_states[vin] = value.value == "4"
            if vin in self.excluded_cars:
                self.ignition_states[vin] = False

        return value

    def _get_car_values_handle_precond_status(
        self, car_detail, class_instance, option, update, vin: str
    ):
        attributes = car_detail.get("attributes", {})

        def _attr_to_bool(attr: dict[str, Any]) -> bool:
            """Coerce legacy/VSU attribute payloads to a boolean state."""
            if not attr:
                return False

            if "bool_value" in attr:
                return bool(attr.get("bool_value"))

            raw_value = attr.get("value")
            if isinstance(raw_value, bool):
                return raw_value
            if isinstance(raw_value, int):
                return raw_value > 0
            if isinstance(raw_value, str):
                lowered = raw_value.lower()
                if lowered in ("true", "false"):
                    return lowered == "true"
                if raw_value.lstrip("-").isdigit():
                    return int(raw_value) > 0

            raw_int = attr.get("int_value")
            if raw_int is not None:
                try:
                    return int(raw_int) > 0
                except (TypeError, ValueError):
                    return False

            return False

        # Retrieve attributes with defaults to handle missing keys
        precond_now_attr = attributes.get("precondNow", {})
        precond_active_attr = attributes.get("precondActive", {})
        precond_operating_mode_attr = attributes.get("precondOperatingMode", {})
        precond_state_attr = attributes.get("precondState", {})
        precond_state_value = (
            precond_state_attr.get("value", {}) if isinstance(precond_state_attr, dict) else {}
        )

        # VSU reports precondNow as an enum attribute and precondState as a
        # nested message, while the legacy VEP path used plain booleans.
        precond_now_value = _attr_to_bool(precond_now_attr)
        precond_active_value = _attr_to_bool(precond_active_attr)
        precond_operating_mode_value = precond_operating_mode_attr.get("int_value", 0)
        precond_operating_mode_bool = int(precond_operating_mode_value) > 0
        precond_state_activation_value = False
        if isinstance(precond_state_value, dict):
            precond_state_activation_value = bool(
                precond_state_value.get("activation_state", False)
            )

        # Calculate precondStatus
        value = (
            precond_now_value
            or precond_active_value
            or precond_operating_mode_bool
            or precond_state_activation_value
        )

        # Determine if any of the attributes are present
        if (
            precond_now_attr
            or precond_active_attr
            or precond_operating_mode_attr
            or precond_state_attr
        ):
            status = "VALID"
            time_stamp = max(
                int(precond_now_attr.get("timestamp", 0)),
                int(precond_active_attr.get("timestamp", 0)),
                int(precond_operating_mode_attr.get("timestamp", 0)),
                int(precond_state_attr.get("timestamp", 0)),
            )
            return CarAttribute(
                value=value,
                retrievalstatus=status,
                timestamp=time_stamp,
                display_value=str(value),
                unit=None,
            )

        if not update:
            # Set status for non-existing values when no update occurs
            return CarAttribute(False, 4, 0)

        return None

    def _get_car_values_handle_temperature_points(
        self, car_detail, class_instance, option: str, update, vin: str
    ):
        curr_zone = option.replace("temperature_points_", "")
        attributes = car_detail.get("attributes", {})
        temperaturePoints = attributes.get("temperaturePoints")
        if not temperaturePoints:
            return None

        time_stamp = temperaturePoints.get("timestamp", 0)
        temperature_points_value = temperaturePoints.get("temperature_points_value", {})
        temperature_points = temperature_points_value.get("temperature_points", [])

        for point in temperature_points:
            # The zone arrives either as the legacy camelCase string ("frontRight")
            # or as the VSU Zone enum ("FRONT_RIGHT"). FRONT_LEFT is the enum default
            # (0) and is omitted by MessageToJson, so a missing zone means front left.
            point_zone = point.get("zone") or "FRONT_LEFT"
            if point_zone.replace("_", "").lower() != curr_zone.lower():
                continue

            temperature = point.get("temperature")
            if isinstance(temperature, dict):
                # VSU shape: temperature is a nested DoubleTemperatureAttribute.
                value = temperature.get("value", 0)
                display_value = temperature.get("display_value")
                unit = temperature.get("unit")
            else:
                # Legacy VEP/REST shape: temperature is a scalar.
                value = temperature if temperature is not None else 0
                display_value = point.get("temperature_display_value")
                unit = temperaturePoints.get("temperature_unit", None)

            return CarAttribute(
                value=value,
                retrievalstatus="VALID",
                timestamp=time_stamp,
                display_value=display_value,
                unit=unit,
            )

        return None

    def _create_synthetic_window_status_overall(self, car_data, vin):
        """Create a synthetic windowStatusOverall based on individual window statuses for REST data."""
        if not car_data.get("attributes"):
            return

        # Debug: Log all available window-related attributes
        # window_attrs_found = [key for key in car_data["attributes"].keys() if "window" in key.lower()]
        # if window_attrs_found:
        #     LOGGER.debug("Available window attributes for %s: %s", loghelper.Mask_VIN(vin), window_attrs_found)
        # else:
        #     LOGGER.debug("No window attributes found in REST data for %s", loghelper.Mask_VIN(vin))

        # Define main window status attributes to check
        main_window_attrs = [
            "windowstatusfrontleft",
            "windowstatusfrontright",
            "windowstatusrearleft",
            "windowstatusrearright",
        ]

        # Check individual window statuses
        window_statuses = []
        latest_timestamp = 0

        for attr_name in main_window_attrs:
            if attr_name in car_data["attributes"]:
                attr_data = car_data["attributes"][attr_name]
                value = attr_data.get("int_value", 0)
                timestamp = attr_data.get("timestamp", 0)

                # Convert timestamp to int for comparison
                try:
                    timestamp = int(timestamp) if timestamp else 0
                    latest_timestamp = max(latest_timestamp, timestamp)
                except (ValueError, TypeError):
                    pass

                # Add to window statuses if value is available
                if value is not None:
                    window_statuses.append(value)

        # Calculate overall status based on individual windows
        # If we have valid window statuses, determine overall state
        if window_statuses:
            # Assume "CLOSED" = 0, "OPEN" = 1 or similar numeric values
            # If all windows are closed (0), overall should be "CLOSED"
            # If any window is open (>0), overall should be "OPEN"
            try:
                numeric_statuses = [int(status) for status in window_statuses if status is not None]
                if numeric_statuses:
                    overall_value = (
                        "OPEN" if any(status != 2 for status in numeric_statuses) else "CLOSED"
                    )
                else:
                    overall_value = "CLOSED"  # Default to closed if no valid data
            except (ValueError, TypeError):
                # If values are not numeric, try string comparison
                overall_value = "CLOSED"
        else:
            # No individual window data available, default to CLOSED
            overall_value = "CLOSED"

        # Create the synthetic windowStatusOverall attribute
        car_data["attributes"]["windowStatusOverall"] = {
            "timestamp": str(latest_timestamp) if latest_timestamp > 0 else "0",
            "bool_value": overall_value == "CLOSED",
            "status": "VALID",  # Use same status as other synthetic attributes
            "timestamp_in_ms": str(latest_timestamp * 1000 + 223),
        }

        LOGGER.debug(
            "Created synthetic windowStatusOverall for %s: %s (based on %d individual windows)",
            loghelper.Mask_VIN(vin),
            overall_value,
            len(window_statuses),
        )

    def _get_car_value(self, class_instance, object_name, attrib_name, default_value):
        return getattr(
            getattr(class_instance, object_name, default_value),
            attrib_name,
            default_value,
        )
