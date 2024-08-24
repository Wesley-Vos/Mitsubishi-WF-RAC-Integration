"""for select component used for horizontal swing."""
# pylint: disable = too-few-public-methods

import logging
from dataclasses import replace

from . import MitsubishiWfRacConfigEntry, MitsubishiWfRacData
from homeassistant.components.climate.const import HVACMode
from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import WfRacEntity
from .wfrac.models.aircon import AirconCommands, HomeLeaveModeSetting
from .coordinator import Device
from .const import (
    DOMAIN,
    SWING_HORIZONTAL_MODE_TRANSLATION,
    NUMBER_OF_PRESET_MODES,
    SUPPORT_SWING_HORIZONTAL_MODES,
    SUPPORT_SWING_MODES,
    SUPPORTED_HVAC_MODES,
    SWING_MODE_TRANSLATION, SWING_3D_AUTO,
    FAN_MODE_TRANSLATION,
    SUPPORTED_FAN_MODES,
    HVAC_TRANSLATION,
)

_LOGGER = logging.getLogger(__name__)

MODE_TO_OPTIONS_MAPPING = {
    "fan_mode": SUPPORTED_FAN_MODES,
    "hvac_mode": SUPPORTED_HVAC_MODES,
    "horizontal_swing_mode": SUPPORT_SWING_HORIZONTAL_MODES,
    "vertical_swing_mode": SUPPORT_SWING_MODES,
}
PARALLEL_UPDATES = 1

# Heating uses the unit's own Heating TempSetting (10.0°C), which matches
# HOME_LEAVE_TEMP_HEAT exactly. Cooling does not: the unit's Cooling
# TempSetting reads 33.0°C, but the temperature actually applied while the
# official app's away-cool mode is running is 31.0°C - so this hardcodes the
# applied value rather than trusting the configured TempSetting, since only
# the applied value is known to flip Vacant.
HOME_LEAVE_TEMP_HEAT = 10.0
HOME_LEAVE_TEMP_COOL = 31.0
# Temperature to restore when leaving Home Leave mode. There's no reliable way
# to recall whatever temperature was set before Home Leave was turned on (the
# unit itself doesn't report it), so this is a plain, reasonable default.
NORMAL_TEMP = 21.0

HOME_LEAVE_MODE_OFF = "off"
HOME_LEAVE_MODE_AWAY_COOL = "away_cool"
HOME_LEAVE_MODE_AWAY_HEAT = "away_heat"

# The app's own 0=auto/1-4=volume index for this feature specifically - see
# HomeLeaveModeSetting.AirFlow in models/aircon.py. rac_parser.py's
# _apply_home_leave_mode() already converts the raw wire byte to this same
# 0-4 index, so the option strings below map straight onto it.
HOME_LEAVE_AIRFLOW_OPTIONS = ["auto", "1", "2", "3", "4"]


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: MitsubishiWfRacConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup select entries"""

    device: Device = entry.runtime_data.device
    data: MitsubishiWfRacData = entry.runtime_data
    _LOGGER.info("Setup Fan, Horizontal and Vertical Select: %s, %s", device.device_name, device.airco_id)
    entities = [HorizontalSwingSelect(device), VerticalSwingSelect(device), FanSpeedSelect(device)]

    # Same VacantProperty capability gate as OccupancyBinarySensor in
    # binary_sensor.py.
    if device.airco.Capabilities.vacant_property:
        entities.append(HomeLeaveModeSelect(device))

    # Same HomeLeaveMode capability gate as the diagnostic sensors removed by
    # _async_remove_home_leave_mode_sensors() in sensor.py.
    if device.airco.Capabilities.home_leave_mode:
        entities.append(HomeLeaveAirFlowSelect(device, "cooling"))
        entities.append(HomeLeaveAirFlowSelect(device, "heating"))

    for i in range(1, NUMBER_OF_PRESET_MODES + 1):
        entities.extend(
            [
                PresetModeSelect(i, mode, data, _hass)
                for mode in MODE_TO_OPTIONS_MAPPING
            ]
        )

    async_add_entities(entities)


class HorizontalSwingSelect(WfRacEntity, SelectEntity):
    """Select component to set the horizontal swing direction of the airco"""

    _attr_translation_key = "horizontal_swing"
    _attr_has_entity_name: bool = True

    def __init__(self, device: Device) -> None:
        super().__init__(device)
        self._attr_entity_registry_enabled_default = device.swing_selects_enabled_default
        self._attr_options = SUPPORT_SWING_HORIZONTAL_MODES
        self._attr_icon = "mdi:weather-dust"
        self._attr_unique_id = (
            f"{DOMAIN}-{self._device.airco_id}-horizontal-swing-direction"
        )
        self.select_option(
            SWING_3D_AUTO
            if self._device.airco.Entrust
            else
            list(SWING_HORIZONTAL_MODE_TRANSLATION.keys())[
                self._device.airco.WindDirectionLR
            ]
        )

    def _update_state(self) -> None:
        self.select_option(
            SWING_3D_AUTO
            if self._device.airco.Entrust
            else
            list(SWING_HORIZONTAL_MODE_TRANSLATION.keys())[
                self._device.airco.WindDirectionLR
            ]
        )

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _swing_auto = option == SWING_3D_AUTO
        if _swing_auto:
            await self._device.async_queue_command(
                {
                    AirconCommands.Entrust: _swing_auto,
                }
            )
        else:
            await self._device.async_queue_command(
                {
                    AirconCommands.WindDirectionLR: SWING_HORIZONTAL_MODE_TRANSLATION[option],
                    AirconCommands.Entrust: False,
                }
            )
        self.select_option(option)

class VerticalSwingSelect(WfRacEntity, SelectEntity):
    """Select component to set the vertical swing direction of the airco"""

    _attr_translation_key = "vertical_swing"
    _attr_has_entity_name: bool = True

    def __init__(self, device: Device) -> None:
        super().__init__(device)
        self._attr_entity_registry_enabled_default = device.swing_selects_enabled_default
        self._attr_options = SUPPORT_SWING_MODES
        self._attr_icon = "mdi:weather-dust"
        self._attr_unique_id = (
            f"{DOMAIN}-{self._device.airco_id}-vertical-swing-direction"
        )
        self.select_option(
            SWING_3D_AUTO
            if self._device.airco.Entrust
            else list(SWING_MODE_TRANSLATION.keys())[
                self._device.airco.WindDirectionUD
            ]
        )

    def _update_state(self) -> None:
        self.select_option(
            SWING_3D_AUTO
            if self._device.airco.Entrust
            else list(SWING_MODE_TRANSLATION.keys())[
                self._device.airco.WindDirectionUD
            ]
        )

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        _swing_auto = option == SWING_3D_AUTO
        if _swing_auto:
            await self._device.async_queue_command(
                {
                    AirconCommands.Entrust: _swing_auto,
                }
            )
        else:
            await self._device.async_queue_command(
                {
                    AirconCommands.WindDirectionUD: SWING_MODE_TRANSLATION[option],
                    AirconCommands.Entrust: False,
                }
            )
        self.select_option(option)

class FanSpeedSelect(WfRacEntity, SelectEntity):
    """Select component to set the fan speed of the airco"""

    _attr_translation_key = "fan_speed"
    _attr_has_entity_name: bool = True

    def __init__(self, device: Device) -> None:
        super().__init__(device)
        self._attr_entity_registry_enabled_default = device.swing_selects_enabled_default
        self._attr_options = SUPPORTED_FAN_MODES
        self._attr_icon = "mdi:fan"
        self._attr_unique_id = f"{DOMAIN}-{self._device.airco_id}-fan-speed"
        self._update_state()

    def _update_state(self) -> None:
        self.select_option(list(FAN_MODE_TRANSLATION.keys())[self._device.airco.AirFlow])

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self._device.async_queue_command(
            {
                AirconCommands.AirFlow: FAN_MODE_TRANSLATION[option]
            }
        )
        self.select_option(option)


class HomeLeaveModeSelect(WfRacEntity, SelectEntity):
    """Select to enter/leave the unit's own Home Leave (vacant property) mode,
    in either direction.

    The official app's away mode has two independent target points (Heat and
    Cool, each with its own Tag-248 threshold/setting - see the home_leave_*
    diagnostic sensors in sensor.py) and flips the same Vacant bit this
    entity reads/writes. See HOME_LEAVE_TEMP_HEAT/_COOL above for the values
    used and why they're hardcoded rather than read from the live Tag-248
    TempSetting.
    """

    _attr_translation_key = "home_leave_mode"
    _attr_has_entity_name: bool = True
    _attr_icon = "mdi:home-export-outline"

    def __init__(self, device: Device) -> None:
        super().__init__(device)
        self._attr_options = [
            HOME_LEAVE_MODE_OFF,
            HOME_LEAVE_MODE_AWAY_COOL,
            HOME_LEAVE_MODE_AWAY_HEAT,
        ]
        self._attr_unique_id = f"{DOMAIN}-{self._device.airco_id}-home-leave-mode"
        self._update_state()

    def _update_state(self) -> None:
        airco = self._device.airco
        if not airco.Vacant:
            self.select_option(HOME_LEAVE_MODE_OFF)
            return
        mode_from_operation = list(HVAC_TRANSLATION.keys())[airco.OperationMode]
        if mode_from_operation == HVACMode.COOL:
            self.select_option(HOME_LEAVE_MODE_AWAY_COOL)
        elif mode_from_operation == HVACMode.HEAT:
            self.select_option(HOME_LEAVE_MODE_AWAY_HEAT)
        else:
            # Vacant set while running in some other mode than the two the
            # away feature itself uses - shouldn't happen, but "off" is a
            # safer fallback than silently claiming a direction that isn't
            # actually active.
            self.select_option(HOME_LEAVE_MODE_OFF)

    def select_option(self, option: str) -> None:
        """Change the selected option."""
        self._attr_current_option = option

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option == HOME_LEAVE_MODE_AWAY_HEAT:
            await self._device.async_queue_command(
                {
                    AirconCommands.Operation: True,
                    AirconCommands.OperationMode: HVAC_TRANSLATION[HVACMode.HEAT],
                    AirconCommands.PresetTemp: HOME_LEAVE_TEMP_HEAT,
                }
            )
        elif option == HOME_LEAVE_MODE_AWAY_COOL:
            await self._device.async_queue_command(
                {
                    AirconCommands.Operation: True,
                    AirconCommands.OperationMode: HVAC_TRANSLATION[HVACMode.COOL],
                    AirconCommands.PresetTemp: HOME_LEAVE_TEMP_COOL,
                }
            )
        else:
            await self._device.async_queue_command(
                {
                    AirconCommands.PresetTemp: NORMAL_TEMP,
                }
            )
        self.select_option(option)


class HomeLeaveAirFlowSelect(WfRacEntity, SelectEntity):
    """Editable Home Leave Mode airflow level (Tag 248) for one direction.

    Replaces the former read-only home_leave_{mode}_air_flow diagnostic
    sensor in sensor.py - same value, but directly writable. Stays unknown
    until Device.async_request_home_leave_mode_status() has been called at
    least once, same as the TempRule/TempSetting HomeLeaveModeNumber
    entities in number.py - see that class's docstring for why writing
    before that is refused rather than guessed at.
    """

    # Disabled by default, same as the diagnostic sensors this replaces - a
    # niche away-mode feature, not everyone with a HomeLeaveMode-capable
    # model wants extra entities on their device page.
    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name: bool = True

    def __init__(self, device: Device, mode: str) -> None:
        super().__init__(device)
        self._mode = mode
        self._attr_translation_key = f"home_leave_{mode}_air_flow"
        self._attr_options = HOME_LEAVE_AIRFLOW_OPTIONS
        self._attr_unique_id = (
            f"{DOMAIN}-{self._device.airco_id}-home-leave-{mode}-air-flow-select"
        )
        self._update_state()

    def _current_setting(self) -> HomeLeaveModeSetting | None:
        return (
            self._device.airco.HomeLeaveModeForCooling
            if self._mode == "cooling"
            else self._device.airco.HomeLeaveModeForHeating
        )

    def _update_state(self) -> None:
        setting = self._current_setting()
        self._attr_current_option = (
            HOME_LEAVE_AIRFLOW_OPTIONS[setting.AirFlow] if setting is not None else None
        )

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        cooling = self._device.airco.HomeLeaveModeForCooling
        heating = self._device.airco.HomeLeaveModeForHeating
        if cooling is None or heating is None:
            raise HomeAssistantError(
                "Home Leave Mode values are unknown yet - call the climate "
                "entity's 'Request Home Leave Mode status' action once "
                "first, the unit doesn't include them in a plain poll.",
                translation_domain=DOMAIN,
                translation_key="home_leave_mode_status_unknown",
            )
        air_flow = HOME_LEAVE_AIRFLOW_OPTIONS.index(option)
        if self._mode == "cooling":
            cooling = replace(cooling, AirFlow=air_flow)
        else:
            heating = replace(heating, AirFlow=air_flow)
        await self._device.async_set_home_leave_mode(cooling, heating)
        self._attr_current_option = option
        self.async_write_ha_state()


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
