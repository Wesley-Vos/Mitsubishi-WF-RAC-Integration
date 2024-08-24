"""The WF-RAC sensor integration."""  # pylint: disable=invalid-name

from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from homeassistant.const import (
    CONF_HOST, 
    CONF_PORT, 
    CONF_NAME, 
    CONF_DEVICE_ID, 
    Platform,
)
from homeassistant.components.climate.const import HVACMode

from .const import CONF_AIRCO_ID, DOMAIN, CONF_OPERATOR_ID, NUMBER_OF_PRESET_MODES
from .wfrac.device import Device

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE, Platform.NUMBER, Platform.SELECT, Platform.SENSOR]

@dataclass
class PresetMode: 
    name: str
    fan_mode: str
    vertical_swing_mode: str
    horizontal_swing_mode: str
    hvac_mode: HVACMode
    temperature: float

@dataclass
class MitsubishiWfRacData:
    device: Device
    preset_modes: dict[int, PresetMode]
    current_preset_mode: str | None

type MitsubishiWfRacConfigEntry = ConfigEntry[MitsubishiWfRacData]

async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry."""

    if entry.version == 1:
        new_data = entry.data.copy()
        new_options = {
            CONF_HOST: new_data.pop(CONF_HOST),
        }

        hass.config_entries.async_update_entry(
            entry, data=new_data, options=new_options, version=2
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: MitsubishiWfRacConfigEntry):
    """Establish connection with mitsubishi-wf-rac."""

    device: str = entry.options[CONF_HOST]
    name: str = entry.data[CONF_NAME]
    device_id: str = entry.data[CONF_DEVICE_ID]
    operator_id: str = entry.data[CONF_OPERATOR_ID]
    port: int = entry.data[CONF_PORT]
    airco_id: str = entry.data[CONF_AIRCO_ID]

    try:
        api = Device(hass, name, device, port, device_id, operator_id, airco_id)
        await api.update()  # initial update to get fresh values

        default_names = {1: "home", 2: "comfort", 3: "boost", 4: "away"}
        preset_modes: dict[int, PresetMode] = {
            i: PresetMode(
                default_names[i],
                "AUTO",
                "LOW",
                "LOW",
                HVACMode.HEAT,
                21,
            )
            for i in range(1, NUMBER_OF_PRESET_MODES + 1)
        }
        entry.runtime_data = MitsubishiWfRacData(api, preset_modes, None)
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.warning("Something whent wrong setting up device [%s] %s", device, ex)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: MitsubishiWfRacConfigEntry) -> bool:
    """Handle unload of entry."""

    # Unload entities for this entry/device.
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    return unload_ok


async def async_remove_entry(hass, entry: MitsubishiWfRacConfigEntry) -> None:
    """Handle removal of an entry."""

    temp_device: Device = entry.runtime_data.device
    try:
        await temp_device.delete_account()
        _LOGGER.info(
            "Deleted operator ID [%s] from airco [%s]",
            temp_device.operator_id,
            temp_device.airco_id,
        )
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.warning(
            "Something whent wrong deleting account from airco [%s] %s",
            temp_device.name,
            ex,
        )
