"""UI setup, options and IP reconfiguration for EBYTE M31 IO."""

from __future__ import annotations

import ipaddress
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .client import (
    ControllerInfo,
    M31Client,
    M31Error,
    ModelRequired,
    UnsupportedModel,
)
from .const import (
    CONF_EXPANSIONS,
    CONF_INPUT_COUNT,
    CONF_INVERTED_INPUTS,
    CONF_MODEL,
    CONF_UNIT_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT_ID,
    DOMAIN,
    MAX_INPUTS,
    MODEL_AUTO,
    NAME,
)
from .models import HOST_MODELS, parse_expansions


def _connection_schema(
    defaults: dict[str, Any], advanced: bool, include_count: bool = False
) -> vol.Schema:
    fields = {
        vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
        vol.Required(CONF_MODEL, default=defaults.get(CONF_MODEL, MODEL_AUTO)): vol.In(
            [MODEL_AUTO, *HOST_MODELS]
        ),
    }
    if advanced:
        fields.update(
            {
                vol.Required(
                    CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(
                    CONF_UNIT_ID, default=defaults.get(CONF_UNIT_ID, DEFAULT_UNIT_ID)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
            }
        )
        if include_count:
            fields[
                vol.Optional(
                    CONF_EXPANSIONS,
                    description={
                        "suggested_value": ", ".join(defaults.get(CONF_EXPANSIONS, []))
                        if isinstance(defaults.get(CONF_EXPANSIONS, []), list)
                        else defaults.get(CONF_EXPANSIONS, ""),
                    },
                )
            ] = str
            fields[
                vol.Required(
                    CONF_INPUT_COUNT, default=defaults.get(CONF_INPUT_COUNT, 0)
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_INPUTS))
    return vol.Schema(fields)


async def _probe(connection: dict[str, Any], input_count: int = 0) -> ControllerInfo:
    client = M31Client(
        connection[CONF_HOST], connection[CONF_PORT], connection[CONF_UNIT_ID]
    )
    try:
        kwargs = {"model_hint": connection.get(CONF_MODEL)}
        if connection.get(CONF_EXPANSIONS):
            kwargs["expansion_models"] = parse_expansions(connection[CONF_EXPANSIONS])
        return await client.identify(input_count, **kwargs)
    finally:
        client.close()


def _connection(data: dict[str, Any]) -> dict[str, Any]:
    """Validate an IPv4/IPv6 address and normalize its representation."""
    connection = {
        CONF_HOST: str(ipaddress.ip_address(data[CONF_HOST].strip().strip("[]"))),
        CONF_PORT: data.get(CONF_PORT, DEFAULT_PORT),
        CONF_UNIT_ID: data.get(CONF_UNIT_ID, DEFAULT_UNIT_ID),
    }
    model = data.get(CONF_MODEL, MODEL_AUTO)
    if model != MODEL_AUTO:
        if model not in HOST_MODELS:
            raise UnsupportedModel(f"Unsupported selected model: {model}")
        connection[CONF_MODEL] = model
    if data.get(CONF_EXPANSIONS):
        connection[CONF_EXPANSIONS] = list(parse_expansions(data[CONF_EXPANSIONS]))
    return connection


class M31ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up a controller by entering its IP address."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> M31OptionsFlow:
        return M31OptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}
        defaults = user_input or {}
        if user_input is not None:
            try:
                connection = _connection(user_input)
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            except UnsupportedModel:
                errors["base"] = "invalid_expansions"
            else:
                # Avoid probing a second copy of an already configured endpoint.
                self._async_abort_entries_match(
                    {
                        key: connection[key]
                        for key in (CONF_HOST, CONF_PORT, CONF_UNIT_ID)
                    }
                )
                try:
                    info = await _probe(connection, user_input.get(CONF_INPUT_COUNT, 0))
                except ModelRequired:
                    errors[CONF_MODEL] = "model_required"
                except UnsupportedModel:
                    errors["base"] = "unsupported_model"
                except M31Error:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(info.mac or _endpoint_id(connection))
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"{NAME} {connection[CONF_HOST]}",
                        data=connection,
                        options={CONF_INPUT_COUNT: user_input.get(CONF_INPUT_COUNT, 0)},
                    )
        return self.async_show_form(
            step_id="user",
            errors=errors,
            data_schema=_connection_schema(
                defaults,
                self.show_advanced_options or bool(errors),
                include_count=True,
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Change the address without replacing entities or automations."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            try:
                connection = _connection(
                    {
                        **user_input,
                        CONF_MODEL: user_input.get(
                            CONF_MODEL, entry.data.get(CONF_MODEL, MODEL_AUTO)
                        ),
                    }
                )
                if CONF_EXPANSIONS in entry.options:
                    connection[CONF_EXPANSIONS] = entry.options[CONF_EXPANSIONS]
                elif CONF_EXPANSIONS in entry.data:
                    connection[CONF_EXPANSIONS] = entry.data[CONF_EXPANSIONS]
            except ValueError:
                errors[CONF_HOST] = "invalid_host"
            except UnsupportedModel:
                errors["base"] = "invalid_expansions"
            else:
                if any(
                    other.entry_id != entry.entry_id
                    and all(
                        other.data.get(key) == value
                        for key, value in connection.items()
                        if key in (CONF_HOST, CONF_PORT, CONF_UNIT_ID)
                    )
                    for other in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                try:
                    info = await _probe(
                        connection, entry.options.get(CONF_INPUT_COUNT, 0)
                    )
                except ModelRequired:
                    errors[CONF_MODEL] = "model_required"
                except UnsupportedModel:
                    errors["base"] = "unsupported_model"
                except M31Error:
                    errors["base"] = "cannot_connect"
                else:
                    if (
                        re.fullmatch(
                            r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", entry.unique_id or ""
                        )
                        and info.mac != entry.unique_id
                    ):
                        return self.async_abort(reason="wrong_device")
                    title = entry.title
                    if title in (
                        f"EBYTE M31 {entry.data[CONF_HOST]}",
                        f"{NAME} {entry.data[CONF_HOST]}",
                    ):
                        title = f"{NAME} {connection[CONF_HOST]}"
                    return self.async_update_reload_and_abort(
                        entry, data=connection, title=title
                    )
        return self.async_show_form(
            step_id="reconfigure",
            errors=errors,
            data_schema=_connection_schema(user_input or dict(entry.data), True),
        )


def _endpoint_id(connection: dict[str, Any]) -> str:
    return f"{connection[CONF_HOST]}:{connection[CONF_PORT]}:{connection[CONF_UNIT_ID]}"


class M31OptionsFlow(config_entries.OptionsFlow):
    """Adjust polling, expansion inventory and digital input polarity."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}
        defaults = dict(self.config_entry.options)
        if user_input is not None:
            defaults.update(user_input)
            # HA omits cleared optional fields. Treat them as empty, rather than
            # restoring a saved value or requiring the frontend to send "".
            inverted_text = user_input.get(CONF_INVERTED_INPUTS, "")
            expansions_text = user_input.get(CONF_EXPANSIONS, "")
            defaults.update(
                {
                    CONF_INVERTED_INPUTS: inverted_text,
                    CONF_EXPANSIONS: expansions_text,
                }
            )
            try:
                expansions = parse_expansions(expansions_text)
            except UnsupportedModel:
                return self.async_show_form(
                    step_id="init",
                    errors={"base": "invalid_expansions"},
                    data_schema=self._options_schema(defaults),
                )
            try:
                inverted = sorted(
                    {
                        int(number.strip())
                        for number in inverted_text.split(",")
                        if number.strip()
                    }
                )
                if any(not 1 <= number <= MAX_INPUTS for number in inverted):
                    raise ValueError
            except ValueError:
                errors[CONF_INVERTED_INPUTS] = "invalid_inputs"
            else:
                try:
                    info = await _probe(
                        {**self.config_entry.data, CONF_EXPANSIONS: list(expansions)},
                        user_input[CONF_INPUT_COUNT],
                    )
                except UnsupportedModel:
                    errors["base"] = "unsupported_model"
                except M31Error:
                    errors["base"] = "cannot_connect"
                else:
                    if any(number > info.input_count for number in inverted):
                        errors[CONF_INVERTED_INPUTS] = "invalid_inputs"
                    else:
                        return self.async_create_entry(
                            title="",
                            data={
                                **user_input,
                                CONF_INVERTED_INPUTS: inverted,
                                CONF_EXPANSIONS: list(expansions),
                            },
                        )
        return self.async_show_form(
            step_id="init", errors=errors, data_schema=self._options_schema(defaults)
        )

    def _options_schema(self, defaults):
        inverted_default = defaults.get(CONF_INVERTED_INPUTS, [])
        if isinstance(inverted_default, list):
            inverted_default = ", ".join(map(str, inverted_default))
        expansions = defaults.get(
            CONF_EXPANSIONS, self.config_entry.data.get(CONF_EXPANSIONS, [])
        )
        if not isinstance(expansions, str):
            expansions = ", ".join(expansions)
        return vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=defaults.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
                vol.Required(
                    CONF_INPUT_COUNT, default=defaults.get(CONF_INPUT_COUNT, 0)
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_INPUTS)),
                vol.Optional(
                    CONF_INVERTED_INPUTS,
                    description={"suggested_value": inverted_default},
                ): str,
                vol.Optional(
                    CONF_EXPANSIONS, description={"suggested_value": expansions}
                ): str,
            }
        )
