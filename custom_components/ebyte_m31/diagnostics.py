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
        "family": coordinator.info.family,
        "firmware": coordinator.info.firmware,
        "input_count": coordinator.info.input_count,
        "digital_outputs": coordinator.info.io_layout.do,
        "analog_inputs": len(coordinator.info.io_layout.ai),
        "analog_outputs": len(coordinator.info.io_layout.ao),
        "pt100_inputs": coordinator.info.io_layout.pt,
        "inventory_source": coordinator.info.inventory_source,
        "modules": list(coordinator.info.modules),
        "last_update_success": coordinator.last_update_success,
        "poll_interval_seconds": coordinator.update_interval.total_seconds(),
    }
