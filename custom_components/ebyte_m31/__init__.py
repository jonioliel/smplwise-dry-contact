"""Home Assistant integration for EBYTE M31 and M31-U digital inputs."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import M31Client, M31Error
from .const import CONF_INPUT_COUNT, CONF_MODEL, CONF_UNIT_ID
from .coordinator import M31Coordinator

PLATFORMS = [Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Connect, validate the inputs, then add all entities."""
    client = M31Client(
        entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_UNIT_ID]
    )
    try:
        info = await client.identify(
            entry.options.get(CONF_INPUT_COUNT, 0),
            model_hint=entry.data.get(CONF_MODEL),
        )
        coordinator = M31Coordinator(hass, entry, client, info)
        await coordinator.async_config_entry_first_refresh()
    except M31Error as err:
        client.close()
        raise ConfigEntryNotReady(str(err)) from err
    except BaseException:
        client.close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(client.close)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply options by reloading the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and close the connection through unload callbacks."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
