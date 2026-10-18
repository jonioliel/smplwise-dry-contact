"""Relay and PNP digital outputs, including expansion cards."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import M31Entity
from .errors import M31Error

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(
        M31Output(coordinator, entry, i) for i in range(coordinator.info.io_layout.do)
    )


class M31Output(M31Entity, SwitchEntity):
    _attr_icon = "mdi:electric-switch"

    def __init__(self, coordinator, entry, index):
        super().__init__(coordinator, entry, "do", index)

    @property
    def is_on(self):
        return self.coordinator.data.do[self._index]

    async def async_turn_on(self, **kwargs):
        await self._set_output(True)

    async def async_turn_off(self, **kwargs):
        await self._set_output(False)

    async def _set_output(self, state):
        if not self.available:
            raise HomeAssistantError("Controller is unavailable")
        try:
            await self.coordinator.client.set_do(
                self.coordinator.info, self._index, state
            )
        except (M31Error, ValueError) as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_request_refresh()
