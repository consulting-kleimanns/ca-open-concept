"""Einrichtung über die Oberfläche: Quellen, Grenzen und Verbraucher."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_GENERATOR_MIN_SOC,
    CONF_GENERATOR_SOC,
    CONF_LANDSTROM,
    CONF_LIMIT_GENERATOR,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_V2L,
    DEFAULT_GENERATOR_MIN_SOC,
    DEFAULT_LIMIT_GENERATOR,
    DEFAULT_LIMIT_LANDSTROM,
    DEFAULT_LIMIT_V2L,
    DOMAIN,
    LOAD_BUS,
    LOAD_NAME,
    LOAD_NOMINAL,
    LOAD_POWER,
    LOAD_SWITCH,
)

SWITCHABLE = ["switch", "light", "input_boolean"]
SOURCE_ENTITIES = (CONF_LANDSTROM, CONF_V2L, CONF_GENERATOR_SOC)


def _watt(max_w: int = 10000) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=max_w, step=50, unit_of_measurement="W", mode=selector.NumberSelectorMode.BOX
        )
    )


def _sources_schema(defaults: dict[str, Any]) -> vol.Schema:
    def opt(key: str) -> vol.Optional:
        value = defaults.get(key)
        return vol.Optional(key, description={"suggested_value": value} if value else None)

    return vol.Schema(
        {
            opt(CONF_LANDSTROM): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            opt(CONF_V2L): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor")
            ),
            opt(CONF_GENERATOR_SOC): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="battery")
            ),
            vol.Required(
                CONF_GENERATOR_MIN_SOC,
                default=defaults.get(CONF_GENERATOR_MIN_SOC, DEFAULT_GENERATOR_MIN_SOC),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")
            ),
            vol.Required(
                CONF_LIMIT_LANDSTROM,
                default=defaults.get(CONF_LIMIT_LANDSTROM, DEFAULT_LIMIT_LANDSTROM),
            ): _watt(),
            vol.Required(
                CONF_LIMIT_V2L, default=defaults.get(CONF_LIMIT_V2L, DEFAULT_LIMIT_V2L)
            ): _watt(),
            vol.Required(
                CONF_LIMIT_GENERATOR,
                default=defaults.get(CONF_LIMIT_GENERATOR, DEFAULT_LIMIT_GENERATOR),
            ): _watt(),
        }
    )


class CamperConfigFlow(ConfigFlow, domain=DOMAIN):
    """Erstes Einrichten: Quellen und Grenzen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Quellen auswählen."""
        if user_input is not None:
            return self.async_create_entry(title="CA Camper", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_sources_schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> CamperOptionsFlow:
        """Optionen: Verbraucher, Quellen und Grenzen."""
        return CamperOptionsFlow()


class CamperOptionsFlow(OptionsFlow):
    """Verbraucher, Quellen und Grenzen pflegen."""

    def _options(self) -> dict[str, Any]:
        return {**self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hauptmenü."""
        return self.async_show_menu(
            step_id="init", menu_options=["add_load", "remove_load", "sources"]
        )

    async def async_step_add_load(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verbraucher hinzufügen."""
        errors: dict[str, str] = {}
        options = self._options()
        loads: list[dict[str, Any]] = list(options.get(CONF_LOADS, []))
        if user_input is not None:
            if any(item[LOAD_SWITCH] == user_input[LOAD_SWITCH] for item in loads):
                errors[LOAD_SWITCH] = "already_configured"
            else:
                load = {
                    LOAD_NAME: user_input[LOAD_NAME],
                    LOAD_SWITCH: user_input[LOAD_SWITCH],
                    LOAD_POWER: user_input.get(LOAD_POWER),
                    LOAD_BUS: user_input[LOAD_BUS],
                    LOAD_NOMINAL: float(user_input[LOAD_NOMINAL]),
                }
                options[CONF_LOADS] = [*loads, load]
                return self.async_create_entry(data=options)

        schema = vol.Schema(
            {
                vol.Required(LOAD_NAME): selector.TextSelector(),
                vol.Required(LOAD_SWITCH): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SWITCHABLE)
                ),
                vol.Optional(LOAD_POWER): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="power")
                ),
                vol.Required(LOAD_BUS, default="komfort"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["primaer", "komfort"], translation_key="bus"
                    )
                ),
                vol.Required(LOAD_NOMINAL, default=0): _watt(),
            }
        )
        return self.async_show_form(step_id="add_load", data_schema=schema, errors=errors)

    async def async_step_remove_load(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verbraucher entfernen."""
        options = self._options()
        loads: list[dict[str, Any]] = list(options.get(CONF_LOADS, []))
        if not loads:
            return self.async_abort(reason="no_loads")
        if user_input is not None:
            remove = set(user_input["loads"])
            options[CONF_LOADS] = [item for item in loads if item[LOAD_SWITCH] not in remove]
            return self.async_create_entry(data=options)
        choices = [
            selector.SelectOptionDict(
                value=item[LOAD_SWITCH], label=f"{item[LOAD_NAME]} ({item[LOAD_SWITCH]})"
            )
            for item in loads
        ]
        schema = vol.Schema(
            {
                vol.Required("loads"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="remove_load", data_schema=schema)

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Quellen und Grenzen ändern."""
        options = self._options()
        if user_input is not None:
            for key in SOURCE_ENTITIES:
                options[key] = user_input.get(key)
            options.update({k: v for k, v in user_input.items() if k not in SOURCE_ENTITIES})
            return self.async_create_entry(data=options)
        current = {**self.config_entry.data, **options}
        return self.async_show_form(step_id="sources", data_schema=_sources_schema(current))
