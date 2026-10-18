"""Analog input and PT100 measurements."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature

from .entity import M31Entity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    layout = coordinator.info.io_layout
    async_add_entities(
        [
            *(
                M31AnalogInput(coordinator, entry, i, kind)
                for i, kind in enumerate(layout.ai)
            ),
            *(M31Temperature(coordinator, entry, i) for i in range(layout.pt)),
        ]
    )


class M31AnalogInput(M31Entity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, entry, index, kind):
        super().__init__(coordinator, entry, "ai", index)
        self._attr_native_unit_of_measurement = "V" if kind == "voltage" else "mA"
        self._attr_device_class = (
            SensorDeviceClass.VOLTAGE
            if kind == "voltage"
            else SensorDeviceClass.CURRENT
        )

    @property
    def native_value(self):
        return self.coordinator.data.ai[self._index]


class M31Temperature(M31Entity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry, index):
        super().__init__(coordinator, entry, "pt100", index)

    @property
    def native_value(self):
        return self.coordinator.data.pt[self._index]

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self):
        return {"channel_status": self.coordinator.data.pt_status[self._index]}
