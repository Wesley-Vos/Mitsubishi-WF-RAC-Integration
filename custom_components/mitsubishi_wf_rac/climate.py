"""for Climate integration."""

from __future__ import annotations
import asyncio
from datetime import timedelta
import logging
from typing import Any

from . import MitsubishiWfRacConfigEntry, MitsubishiWfRacData, PresetMode
import voluptuous as vol

from homeassistant.components.climate import ClimateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.climate.const import HVACMode, FAN_AUTO
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.util import Throttle
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.restore_state import RestoreEntity

from .wfrac.device import MIN_TIME_BETWEEN_UPDATES, Device
from .wfrac.models.aircon import AirconCommands
from .const import (
    DOMAIN,
    FAN_MODE_TRANSLATION,
    HVAC_TRANSLATION,
    SERVICE_SET_HORIZONTAL_SWING_MODE,
    SERVICE_SET_VERTICAL_SWING_MODE,
    SUPPORT_FLAGS,
    SWING_HORIZONTAL_AUTO,
    SWING_VERTICAL_AUTO,
    SUPPORT_SWING_MODES,
    SUPPORTED_FAN_MODES,
    SUPPORTED_HVAC_MODES,
    SWING_3D_AUTO,
    SWING_MODE_TRANSLATION,
    HORIZONTAL_SWING_MODE_TRANSLATION,
)

_LOGGER = logging.getLogger(__name__)
UPDATE_CONSOLIDATION_PERIOD = timedelta(milliseconds=500)


async def async_setup_entry(hass, entry: MitsubishiWfRacConfigEntry, async_add_entities):
    """Setup climate entities"""
    data: MitsubishiWfRacData = entry.runtime_data
    _LOGGER.info("Setup climate for: %s, %s", data.device.name, data.device.airco_id)
    async_add_entities([AircoClimate(data, hass)])

    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        SERVICE_SET_HORIZONTAL_SWING_MODE,
        {
            vol.Required("swing_mode"): cv.string,
        },
        "async_set_horizontal_swing_mode",
    )

    platform.async_register_entity_service(
        SERVICE_SET_VERTICAL_SWING_MODE,
        {
            vol.Required("swing_mode"): cv.string,
        },
        "async_set_swing_mode",
    )


class AircoClimate(ClimateEntity, RestoreEntity):
    """Representation of a climate entity"""

    _attr_supported_features: int = SUPPORT_FLAGS
    _attr_temperature_unit: str = UnitOfTemperature.CELSIUS
    _attr_hvac_modes: list[HVACMode] = SUPPORTED_HVAC_MODES
    _attr_fan_modes: list[str] = SUPPORTED_FAN_MODES
    _attr_hvac_mode: HVACMode = HVACMode.OFF
    _attr_fan_mode: str = FAN_AUTO
    _attr_swing_mode: str | None = SWING_VERTICAL_AUTO
    _attr_swing_modes: list[str] | None = SUPPORT_SWING_MODES
    _attr_min_temp: float = 16
    _attr_max_temp: float = 30
    _attr_horizontal_swing_mode: str | None = SWING_HORIZONTAL_AUTO
    _enable_turn_on_off_backwards_compatibility = False  # Remove after HA 2025.1

    def __init__(self, data: MitsubishiWfRacData, hass: HomeAssistant) -> None:
        self._data = data
        self._device = data.device
        self._hass = hass

        self._attr_name = self._device.name
        self._attr_device_info = self._device.device_info
        self._attr_unique_id = f"{DOMAIN}-{self._device.airco_id}-climate"
        self._consolidated_params = {}
        self._update_state()

    async def async_added_to_hass(self):
        """Register for sensor updates."""
        self._data.current_preset_mode = self._data.preset_modes[1].name
    
    @property
    def extra_state_attributes(self):
        return {
                "hvac_mode_state": self._attr_hvac_mode,
                "horizontal_swing_mode": self._attr_horizontal_swing_mode
               }

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        set_temp = kwargs.get(ATTR_TEMPERATURE)
        if set_temp is None:
            raise ValueError("Temperature is required")

        if set_temp < self._attr_min_temp:
            raise ValueError(f"Temperature {set_temp} is below minimum {self._attr_min_temp}")

        if set_temp > self._attr_max_temp:
            raise ValueError(f"Temperature {set_temp} is above maximum {self._attr_max_temp}")

        opts: dict[str, Any] = {AirconCommands.PresetTemp: set_temp}

        if "hvac_mode" in kwargs:
            hvac_mode: HVACMode | None = kwargs.get("hvac_mode")
            hvac_mode = HVACMode.OFF if hvac_mode is None else hvac_mode
            opts.update(
                {
                    AirconCommands.OperationMode: self._device.airco.OperationMode
                    if hvac_mode == HVACMode.OFF
                    else HVAC_TRANSLATION[hvac_mode],
                    AirconCommands.Operation: hvac_mode != HVACMode.OFF,
                }
            )

        await self._set_airco(opts)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        await self._set_airco({AirconCommands.AirFlow: FAN_MODE_TRANSLATION[fan_mode]})

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self._set_airco({AirconCommands.Operation: True})

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        await self._set_airco(
            {
                AirconCommands.OperationMode: self._device.airco.OperationMode
                if hvac_mode == HVACMode.OFF
                else HVAC_TRANSLATION[hvac_mode],
                AirconCommands.Operation: hvac_mode != HVACMode.OFF,
            }
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation."""
        _airco = self._device.airco
        _swing_auto = swing_mode == SWING_3D_AUTO
        _swing_lr = (
            HORIZONTAL_SWING_MODE_TRANSLATION[SWING_HORIZONTAL_AUTO]
            if self._device.airco.Entrust
            else self._device.airco.WindDirectionLR
        )
        _swing_ud = _airco.WindDirectionUD

        if swing_mode != SWING_3D_AUTO:
            _swing_ud = SWING_MODE_TRANSLATION[swing_mode]

        await self._set_airco(
            {
                AirconCommands.WindDirectionUD: _swing_ud,
                AirconCommands.WindDirectionLR: _swing_lr,
                AirconCommands.Entrust: _swing_auto,
            }
        )

    async def async_set_horizontal_swing_mode(self, swing_mode: str) -> None:
        """Set new target horizontal swing operation."""
        _airco = self._device.airco
        _swing_lr = HORIZONTAL_SWING_MODE_TRANSLATION[swing_mode]
        _swing_ud = (
            HORIZONTAL_SWING_MODE_TRANSLATION[SWING_VERTICAL_AUTO]
            if self._device.airco.Entrust
            else self._device.airco.WindDirectionUD
        )

        _LOGGER.debug("airco: %s", _airco)

        await self._set_airco(
            {
                AirconCommands.WindDirectionUD: _swing_ud,
                AirconCommands.WindDirectionLR: _swing_lr,
                # always set to false otherwise service won't have effect
                AirconCommands.Entrust: False,
            }
        )

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self._set_airco({AirconCommands.Operation: False})

    async def _set_airco(self, params: dict[str, Any]) -> None:
        will_do_update = not self._consolidated_params
        self._consolidated_params.update(params)

        if will_do_update:
            self._hass.async_create_task(self._set_airco_after_delay())

    async def _set_airco_after_delay(self):
        await asyncio.sleep(UPDATE_CONSOLIDATION_PERIOD.total_seconds())
        params = self._consolidated_params.copy()
        self._consolidated_params.clear()
        await self._device.set_airco(params)
        self._update_state()
        self.async_write_ha_state()

    @property
    def preset_mode(self):
        """Return the current preset mode"""
        self.determine_preset_mode()
        return self._data.current_preset_mode

    @property
    def preset_modes(self):
        """Return a list of available preset modes."""
        return [mode.name for mode in self._data.preset_modes.values()]

    def determine_preset_mode(self) -> str | None:
        """Method to determine preset mode"""
        # _LOGGER.error("Determine preset mode")

        self._data.current_preset_mode = None
        for mode in self._data.preset_modes.values():
            # _LOGGER.error("Try mode: %s", mode[NAME])

            if self._is_current_mode(mode):
                # _LOGGER.error("Determined preset mode: %s", mode[NAME])
                self._data.current_preset_mode = mode.name
                break

    def _is_current_mode(self, mode: PresetMode):
        # _LOGGER.error("Is current mode %s?", mode.name)
        if mode.hvac_mode == HVACMode.OFF:
            return mode.hvac_mode == self._attr_hvac_mode
        if mode.temperature != self._attr_target_temperature:
            return False
        if mode.fan_mode != self._attr_fan_mode:
            return False
        if mode.vertical_swing_mode != self._attr_swing_mode:
            return False
        if mode.vertical_swing_mode != SWING_3D_AUTO and mode.horizontal_swing_mode != self._attr_horizontal_swing_mode:
            return False

        return True

    async def async_set_preset_mode(self, preset_mode):
        """Set new preset mode."""
        self._data.current_preset_mode = preset_mode
        # self.async_write_ha_state()

        preset_mode_obj: PresetMode | None = next((obj for obj in self._data.preset_modes.values() if obj.name == preset_mode), None)
        if preset_mode_obj is None:
            return
        
        if preset_mode_obj.hvac_mode == HVACMode.OFF:
            await self.async_set_hvac_mode(preset_mode_obj.hvac_mode)
        else:
            opts = {
                AirconCommands.Operation: True,
                AirconCommands.PresetTemp: preset_mode_obj.temperature,
                AirconCommands.AirFlow: FAN_MODE_TRANSLATION[preset_mode_obj.fan_mode],

            }

            vertical_swing_mode = preset_mode_obj.vertical_swing_mode
            horizontal_swing_mode = preset_mode_obj.horizontal_swing_mode
            _swing_auto = vertical_swing_mode == SWING_3D_AUTO
            _swing_lr = (
                HORIZONTAL_SWING_MODE_TRANSLATION[SWING_HORIZONTAL_AUTO]
                if _swing_auto
                else HORIZONTAL_SWING_MODE_TRANSLATION[horizontal_swing_mode]
            )
            _swing_ud = self._device.airco.WindDirectionUD

            if vertical_swing_mode != SWING_3D_AUTO:
                _swing_ud = SWING_MODE_TRANSLATION[vertical_swing_mode]

            opts.update({
                AirconCommands.WindDirectionUD: _swing_ud,
                AirconCommands.WindDirectionLR: _swing_lr,
                AirconCommands.Entrust: _swing_auto,
            })

            # _LOGGER.error(opts)

            await self._device.set_airco(opts)
            self._update_state()


    def _update_state(self) -> None:
        """Private update attributes"""
        airco = self._device.airco

        self._attr_target_temperature = (
            airco.PresetTemp if hasattr(airco, "PresetTemp") else None
        )
        self._attr_current_temperature = (
            airco.IndoorTemp if hasattr(airco, "IndoorTemp") else None
        )
        self._attr_fan_mode = (
            list(FAN_MODE_TRANSLATION.keys())[airco.AirFlow]
            if hasattr(airco, "AirFlow")
            else None
        )
        self._attr_swing_mode = (
            (
                SWING_3D_AUTO
                if airco.Entrust
                else list(SWING_MODE_TRANSLATION.keys())[airco.WindDirectionUD]
            )
            if hasattr(airco, "Entrust") and hasattr(airco, "WindDirectionUD")
            else None
        )
        self._attr_horizontal_swing_mode = (
            list(HORIZONTAL_SWING_MODE_TRANSLATION.keys())[airco.WindDirectionLR]
            if hasattr(airco, "WindDirectionLR")
            else None
        )
        self._attr_available = self._device.available
        self._attr_hvac_mode = list(HVAC_TRANSLATION.keys())[airco.OperationMode] if hasattr(airco, 'OperationMode') else None

        if hasattr(airco, 'Operation'):
            if airco.Operation is False:
                self._attr_hvac_mode = HVACMode.OFF
            else:
                _new_mode: HVACMode = HVACMode.OFF
                _mode = airco.OperationMode
                if _mode == 0:
                    _new_mode = HVACMode.AUTO
                elif _mode == 1:
                    _new_mode = HVACMode.COOL
                elif _mode == 2:
                    _new_mode = HVACMode.HEAT
                elif _mode == 3:
                    _new_mode = HVACMode.FAN_ONLY
                elif _mode == 4:
                    _new_mode = HVACMode.DRY
                self._attr_hvac_mode = _new_mode
        else:
            self._attr_hvac_mode = None

        self.determine_preset_mode()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Retrieve latest state."""
        try:
            await self._device.update()
            self._update_state()
        except Exception: # pylint: disable=broad-except
            _LOGGER.warning("Could not update the airco values")
            self._attr_available = False
            self._device.set_available(False)
            self.async_write_ha_state()
