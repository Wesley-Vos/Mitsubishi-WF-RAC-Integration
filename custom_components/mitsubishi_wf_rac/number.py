""" for number component used for preset mode temperature."""
# pylint: disable = too-few-public-methods

import logging

from . import MitsubishiWfRacConfigEntry, MitsubishiWfRacData
from homeassistant.components.number import NumberEntity, RestoreNumber

from .const import (
    DOMAIN,
    NUMBER_OF_PRESET_MODES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry: MitsubishiWfRacConfigEntry, async_add_entities):
    """Setup text entries"""
    data = entry.runtime_data

    _LOGGER.info("Setup text: %s, %s", data.device.name, data.device.airco_id)
    entities: list[NumberEntity] = []

    entities.extend(
        [
            PresetModeNumber(i, data, hass)
            for i in range(1, NUMBER_OF_PRESET_MODES + 1)
        ]
    )

    async_add_entities(entities)

class PresetModeNumber(RestoreNumber, NumberEntity):
    """Preset mode number"""

    def __init__(self, i, data: MitsubishiWfRacData, hass):
        self._hass = hass
        super().__init__()

        self._data = data
        self.i = i
        self._attr_name = f"{DOMAIN} preset mode { i } temperature"
        self._attr_unique_id = f"number_{DOMAIN}_{i}_temperature"
        self._state = 0

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        state = await self.async_get_last_number_data()
        if state and state.native_value:
            self._data.preset_modes[self.i].temperature = state.native_value

    @property
    def native_min_value(self) -> float:
        return 18

    @property
    def native_max_value(self) -> float:
        return 30

    @property
    def native_step(self) -> float:
        return 1

    @property
    def native_value(self) -> float:
        """Return the state of the entity."""
        return self._data.preset_modes[self.i].temperature

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self._data.preset_modes[self.i].temperature = value
        self.async_write_ha_state()