"""for select component used for horizontal swing."""
# pylint: disable = too-few-public-methods

import logging

from . import MitsubishiWfRacConfigEntry, MitsubishiWfRacData
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .wfrac.models.aircon import AirconCommands
from .wfrac.device import Device
from .const import (
    DOMAIN,
    HORIZONTAL_SWING_MODE_TRANSLATION,
    NUMBER_OF_PRESET_MODES,
    SUPPORT_HORIZONTAL_SWING_MODES,
    SUPPORT_SWING_MODES,
    SUPPORTED_FAN_MODES,
    SUPPORTED_HVAC_MODES,
    SWING_3D_AUTO,
    SWING_HORIZONTAL_AUTO,
    SWING_MODE_TRANSLATION,
)

_LOGGER = logging.getLogger(__name__)

MODE_TO_OPTIONS_MAPPING = {
    "fan_mode": SUPPORTED_FAN_MODES,
    "hvac_mode": SUPPORTED_HVAC_MODES,
    "horizontal_swing_mode": SUPPORT_HORIZONTAL_SWING_MODES,
    "vertical_swing_mode": SUPPORT_SWING_MODES,
}


async def async_setup_entry(
    hass, entry: MitsubishiWfRacConfigEntry, async_add_entities
):
    """Setup select entries"""

    data: MitsubishiWfRacData = entry.runtime_data
    _LOGGER.info(
        "Setup Horizontal and Vertical Select: %s, %s",
        data.device.name,
        data.device.airco_id,
    )
    entities = [HorizontalSwingSelect(data.device), VerticalSwingSelect(data.device)]

    for i in range(1, NUMBER_OF_PRESET_MODES + 1):
        entities.extend(
            [PresetModeSelect(i, mode, data, hass) for mode in MODE_TO_OPTIONS_MAPPING]
        )
    async_add_entities(entities)


class HorizontalSwingSelect(SelectEntity):
    """Select component to set the horizontal swing direction of the airco"""

    def __init__(self, device: Device) -> None:
        super().__init__()
        self._attr_options = SUPPORT_HORIZONTAL_SWING_MODES
        self._device = device
        self._attr_name = f"{device.name} horizontal swing direction"
        self._attr_device_info = device.device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_unique_id = (
            f"{DOMAIN}-{self._device.airco_id}-horizontal-swing-direction"
        )
        if hasattr(self._device.airco, "WindDirectionLR"):
            self.select_option(
                list(HORIZONTAL_SWING_MODE_TRANSLATION.keys())[
                    self._device.airco.WindDirectionLR
                ]
            )
            self._attr_available = self._device.available
        else:
            self.select_option(None)
            self._attr_available = False

    def _update_state(self) -> None:
        if hasattr(self._device.airco, "WindDirectionLR"):
            self.select_option(
                list(HORIZONTAL_SWING_MODE_TRANSLATION.keys())[
                    self._device.airco.WindDirectionLR
                ]
            )
            self._attr_available = self._device.available
        else:
            self.select_option(None)
            self._attr_available = False

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._device.set_airco(
            {AirconCommands.WindDirectionLR: HORIZONTAL_SWING_MODE_TRANSLATION[option]}
        )
        self.select_option(option)

    async def async_update(self):
        """Retrieve latest state."""
        self._update_state()


class VerticalSwingSelect(SelectEntity):
    """Select component to set the vertical swing direction of the airco"""

    def __init__(self, device: Device) -> None:
        super().__init__()
        self._attr_options = SUPPORT_SWING_MODES
        self._device = device
        self._attr_name = f"{device.name} vertical swing direction"
        self._attr_device_info = device.device_info
        self._attr_icon = "mdi:weather-dust"
        self._attr_unique_id = (
            f"{DOMAIN}-{self._device.airco_id}-vertical-swing-direction"
        )
        if hasattr(self._device.airco, "WindDirectionUD"):
            self.select_option(
                list(SWING_MODE_TRANSLATION.keys())[self._device.airco.WindDirectionUD]
            )
            self._attr_available = self._device.available
        else:
            self.select_option(None)
            self._attr_available = False

    def _update_state(self) -> None:
        if hasattr(self._device.airco, "WindDirectionUD"):
            self.select_option(
                SWING_3D_AUTO
                if self._device.airco.Entrust
                else list(SWING_MODE_TRANSLATION.keys())[
                    self._device.airco.WindDirectionUD
                ]
            )
            self._attr_available = self._device.available
        else:
            self.select_option(None)
            self._attr_available = False

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _airco = self._device.airco
        _swing_auto = option == SWING_3D_AUTO
        _swing_lr = (
            HORIZONTAL_SWING_MODE_TRANSLATION[SWING_HORIZONTAL_AUTO]
            if self._device.airco.Entrust
            else self._device.airco.WindDirectionLR
        )
        _swing_ud = _airco.WindDirectionUD

        if option != SWING_3D_AUTO:
            _swing_ud = SWING_MODE_TRANSLATION[option]

        await self._device.set_airco(
            {
                AirconCommands.WindDirectionUD: _swing_ud,
                AirconCommands.WindDirectionLR: _swing_lr,
                AirconCommands.Entrust: _swing_auto,
            }
        )
        self.select_option(option)

    async def async_update(self):
        """Retrieve latest state."""
        self._update_state()


class PresetModeSelect(SelectEntity, RestoreEntity):
    """Preset mode selects for swing and fan speed"""

    def __init__(self, i, mode, data: MitsubishiWfRacData, hass):
        self._hass = hass
        super().__init__()

        self._data = data
        self.i = i
        self.mode = mode

        # self.zone_variable = zone_variable
        self._attr_name = f"{DOMAIN} preset mode { i } { mode }"
        self._attr_unique_id = f"select_{DOMAIN}_{i}_{mode}"

        self._attr_available = True
        # self._current_option = None

        self._options = MODE_TO_OPTIONS_MAPPING[mode]

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()
        if state and state.state in self._options:
            setattr(self._data.preset_modes[self.i], self.mode, state.state)

    @property
    def options(self) -> list[str]:
        """Return the available options."""
        return self._options

    @property
    def current_option(self) -> str:
        """Return current options."""
        return getattr(self._data.preset_modes[self.i], self.mode)

    async def async_select_option(self, option: str) -> None:
        """Select new (option)."""
        setattr(self._data.preset_modes[self.i], self.mode, option)
        self.async_write_ha_state()