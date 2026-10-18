"""Analog output engineering values in mA or V."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError

from .entity import M31Entity
from .errors import M31Error
from .io import ao_limits

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        M31AnalogOutput(coordinator, entry, i, kind)
        for i, kind in enumerate(coordinator.info.io_layout.ao)
    )


class M31AnalogOutput(M31Entity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_step = 0.001
    _attr_icon = "mdi:tune-vertical"

    def __init__(self, coordinator, entry, index, kind):
        super().__init__(coordinator, entry, "ao", index)
        self._kind = kind
        self._attr_native_unit_of_measurement = "V" if kind == "voltage" else "mA"

    @property
    def native_value(self):
        return self.coordinator.data.ao[self._index]

    @property
    def native_min_value(self):
        return ao_limits(self._kind, self.coordinator.data.ao_ranges[self._index])[0]

    @property
    def native_max_value(self):
        return ao_limits(self._kind, self.coordinator.data.ao_ranges[self._index])[1]

    async def async_set_native_value(self, value):
        if not self.available:
            raise HomeAssistantError("Controller is unavailable")
        try:
            await self.coordinator.client.set_ao(
                self.coordinator.info, self._index, value
            )
        except (M31Error, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
