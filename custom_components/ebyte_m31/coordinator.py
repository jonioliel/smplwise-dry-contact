"""Fetch all digital inputs and check IO bus health each poll."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ControllerInfo, M31Client, M31Error
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .io import IOState

_LOGGER = logging.getLogger(__name__)


class M31Coordinator(DataUpdateCoordinator[IOState]):
    """Coordinate input state and availability."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: M31Client,
        info: ControllerInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
            always_update=False,
        )
        self.client = client
        self.info = info
        self.identity = entry.unique_id or entry.entry_id

    async def _async_update_data(self) -> IOState:
        try:
            return await self.client.read_io(self.info)
        except M31Error as err:
            raise UpdateFailed(str(err)) from err
