"""One binary sensor for each physical digital input."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INVERTED_INPUTS, DOMAIN
from .coordinator import M31Coordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the detected input entities."""
    coordinator: M31Coordinator = entry.runtime_data
    inverted = set(entry.options.get(CONF_INVERTED_INPUTS, []))
    async_add_entities(
        M31Input(coordinator, entry, index, index + 1 in inverted)
        for index in range(coordinator.info.input_count)
    )


class M31Input(CoordinatorEntity[M31Coordinator], BinarySensorEntity):
    """A digital input; connectivity failures are unavailable, never off."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:electric-switch"

    def __init__(
        self,
        coordinator: M31Coordinator,
        entry: ConfigEntry,
        index: int,
        inverted: bool,
    ) -> None:
        super().__init__(coordinator)
        self._index = index
        self._inverted = inverted
        self._attr_name = f"DI {index + 1}"
        self._attr_unique_id = f"{coordinator.identity}_di_{index + 1}"
        host = entry.data[CONF_HOST]
        if ":" in host:
            host = f"[{host}]"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.identity)},
            name=entry.title,
            manufacturer="EBYTE",
            model=coordinator.info.model,
            sw_version=coordinator.info.firmware,
            configuration_url=f"http://{host}",
        )

    @property
    def is_on(self) -> bool:
        """Read the input and optionally invert a normally closed contact."""
        return self.coordinator.data[self._index] != self._inverted

    @property
    def extra_state_attributes(self) -> dict[str, int | bool]:
        return {"input_number": self._index + 1, "inverted": self._inverted}
