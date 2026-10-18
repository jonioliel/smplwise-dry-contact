"""Explicit HA interface doubles for logic tests on Windows.

These do not simulate the Home Assistant runtime, registries or frontend.
They test our flow decisions and entity state with the public method shapes.
"""

import sys
from types import ModuleType, SimpleNamespace


class AbortFlow(Exception):
    def __init__(self, reason):
        self.reason = reason


class ConfigEntryNotReady(Exception):
    pass


class UpdateFailed(Exception):
    pass


class HomeAssistantError(Exception):
    pass


class Entry:
    def __init__(
        self, data=None, options=None, unique_id="02:11:22:33:44:55", entry_id="entry"
    ):
        self.data = data or {"host": "192.168.99.99", "port": 502, "unit_id": 1}
        self.options = options or {}
        self.unique_id = unique_id
        self.entry_id = entry_id
        self.title = f"EBYTE M31 {self.data['host']}"
        self.callbacks = []
        self.listeners = []

    def async_on_unload(self, callback):
        self.callbacks.append(callback)

    def add_update_listener(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)


class Flow:
    def __init_subclass__(cls, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)

    def __init__(self):
        self.show_advanced_options = False
        self.entries = []
        self.unique_id = None

    async def async_set_unique_id(self, unique_id):
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self):
        if any(entry.unique_id == self.unique_id for entry in self.entries):
            raise AbortFlow("already_configured")

    def _async_abort_entries_match(self, connection):
        if any(
            all(entry.data.get(key) == value for key, value in connection.items())
            for entry in self.entries
        ):
            raise AbortFlow("already_configured")

    def _async_current_entries(self):
        return self.entries

    def _get_reconfigure_entry(self):
        return self.entry

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, reason):
        return {"type": "abort", "reason": reason}

    def async_update_reload_and_abort(
        self, entry, *, data=None, data_updates=None, title
    ):
        entry.data = (
            dict(data) if data is not None else {**entry.data, **(data_updates or {})}
        )
        entry.title = title
        return self.async_abort(reason="reconfigure_successful")


class Coordinator:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, **kwargs):
        self.update_interval = kwargs["update_interval"]
        self.last_update_success = True

    async def async_config_entry_first_refresh(self):
        try:
            self.data = await self._async_update_data()
        except UpdateFailed as err:
            raise ConfigEntryNotReady(str(err)) from err

    async def async_request_refresh(self):
        self.data = await self._async_update_data()


class CoordinatorEntity:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


def install():
    """Install minimal named interface doubles before loading HA modules."""
    definitions = {
        "homeassistant": {},
        "homeassistant.config_entries": {
            "ConfigFlow": Flow,
            "OptionsFlow": Flow,
            "ConfigEntry": Entry,
        },
        "homeassistant.const": {
            "CONF_HOST": "host",
            "CONF_PORT": "port",
            "CONF_SCAN_INTERVAL": "scan_interval",
            "Platform": SimpleNamespace(
                BINARY_SENSOR="binary_sensor",
                SENSOR="sensor",
                SWITCH="switch",
                NUMBER="number",
            ),
            "UnitOfTemperature": SimpleNamespace(CELSIUS="°C"),
        },
        "homeassistant.core": {
            "callback": lambda function: function,
            "HomeAssistant": object,
        },
        "homeassistant.data_entry_flow": {"FlowResult": dict},
        "homeassistant.exceptions": {
            "ConfigEntryNotReady": ConfigEntryNotReady,
            "HomeAssistantError": HomeAssistantError,
        },
        "homeassistant.helpers": {},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": Coordinator,
            "UpdateFailed": UpdateFailed,
            "CoordinatorEntity": CoordinatorEntity,
        },
        "homeassistant.helpers.device_registry": {"DeviceInfo": dict},
        "homeassistant.helpers.entity_platform": {"AddEntitiesCallback": object},
        "homeassistant.components": {},
        "homeassistant.components.binary_sensor": {
            "BinarySensorEntity": type("BinarySensorEntity", (), {})
        },
        "homeassistant.components.sensor": {
            "SensorEntity": type("SensorEntity", (), {}),
            "SensorDeviceClass": SimpleNamespace(
                CURRENT="current", VOLTAGE="voltage", TEMPERATURE="temperature"
            ),
            "SensorStateClass": SimpleNamespace(MEASUREMENT="measurement"),
        },
        "homeassistant.components.switch": {
            "SwitchEntity": type("SwitchEntity", (), {})
        },
        "homeassistant.components.number": {
            "NumberEntity": type("NumberEntity", (), {}),
            "NumberMode": SimpleNamespace(BOX="box"),
        },
    }
    for name, attributes in definitions.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module
    sys.modules["homeassistant"].config_entries = sys.modules[
        "homeassistant.config_entries"
    ]
