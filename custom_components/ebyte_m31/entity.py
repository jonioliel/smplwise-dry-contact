"""Common controller device identity for IO entities."""

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import M31Coordinator


class M31Entity(CoordinatorEntity[M31Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, kind, index):
        super().__init__(coordinator)
        self._index = index
        self._attr_name = f"{kind.upper()} {index + 1}"
        self._attr_unique_id = f"{coordinator.identity}_{kind}_{index + 1}"
        host = entry.data[CONF_HOST]
        host = f"[{host}]" if ":" in host else host
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.identity)},
            name=entry.title,
            manufacturer="EBYTE",
            model=coordinator.info.model,
            sw_version=coordinator.info.firmware,
            configuration_url=f"http://{host}",
        )
