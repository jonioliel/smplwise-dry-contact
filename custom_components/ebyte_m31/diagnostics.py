"""Redacted diagnostics for troubleshooting IO discovery."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Expose metadata without addresses, MACs or input states."""
    coordinator = entry.runtime_data
    return {
        "model": coordinator.info.model,
        "firmware": coordinator.info.firmware,
        "input_count": coordinator.info.input_count,
        "modules": list(coordinator.info.modules),
        "last_update_success": coordinator.last_update_success,
        "poll_interval_seconds": coordinator.update_interval.total_seconds(),
    }
