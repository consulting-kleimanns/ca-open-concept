"""Einrichtung über die Oberfläche: Quellen, Grenzen, Verbraucher, Verriegelungen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BLUETTI_MIN_SOC,
    CONF_BLUETTI_SOC,
    CONF_INTERLOCKS,
    CONF_LANDSTROM,
    CONF_LIMIT_BLUETTI,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_SHED_DELAY,
    CONF_V2L,
    DEFAULT_BLUETTI_MIN_SOC,
    DEFAULT_LIMIT_BLUETTI,
    DEFAULT_LIMIT_LANDSTROM,
    DEFAULT_LIMIT_V2L,
    DEFAULT_SHED_DELAY,
    DOMAIN,
    LOAD_BUS,
    LOAD_ID,
    LOAD_NAME,
    LOAD_NOMINAL,
    LOAD_POWER,
    LOAD_PRIORITY,
    LOAD_SHEDDABLE,
    LOAD_SWITCH,
    LOCK_A,
    LOCK_B,
)

SWITCHABLE = ["switch", "light", "input_boolean"]


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
            opt(CONF_BLUETTI_SOC): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="battery")
            ),
            vol.Required(
                CONF_BLUETTI_MIN_SOC,
                default=defaults.get(CONF_BLUETTI_MIN_SOC, DEFAULT_BLUETTI_MIN_SOC),
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
                CONF_LIMIT_BLUETTI, default=defaults.get(CONF_LIMIT_BLUETTI, DEFAULT_LIMIT_BLUETTI)
            ): _watt(),
            vol.Required(
                CONF_SHED_DELAY, default=defaults.get(CONF_SHED_DELAY, DEFAULT_SHED_DELAY)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=60, step=1, unit_of_measurement="s")
            ),
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
        """Optionen: Verbraucher und Verriegelungen."""
        return CamperOptionsFlow()


class CamperOptionsFlow(OptionsFlow):
    """Verbraucher, Verriegelungen und Grenzen pflegen."""

    def _options(self) -> dict[str, Any]:
        return {**self.config_entry.options}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Hauptmenü."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_load",
                "remove_load",
                "add_interlock",
                "remove_interlock",
                "sources",
            ],
        )

    async def async_step_add_load(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verbraucher hinzufügen."""
        errors: dict[str, str] = {}
        options = self._options()
        loads: list[dict[str, Any]] = list(options.get(CONF_LOADS, []))
        if user_input is not None:
            if any(l[LOAD_SWITCH] == user_input[LOAD_SWITCH] for l in loads):
                errors[LOAD_SWITCH] = "already_configured"
            else:
                load = {
                    LOAD_ID: user_input[LOAD_NAME],
                    LOAD_NAME: user_input[LOAD_NAME],
                    LOAD_SWITCH: user_input[LOAD_SWITCH],
                    LOAD_POWER: user_input.get(LOAD_POWER),
                    LOAD_BUS: user_input[LOAD_BUS],
                    LOAD_PRIORITY: int(user_input[LOAD_PRIORITY]),
                    LOAD_NOMINAL: float(user_input[LOAD_NOMINAL]),
                    LOAD_SHEDDABLE: user_input[LOAD_SHEDDABLE],
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
                vol.Required(LOAD_PRIORITY, default=5): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=10, step=1)
                ),
                vol.Required(LOAD_NOMINAL, default=0): _watt(),
                vol.Required(LOAD_SHEDDABLE, default=True): selector.BooleanSelector(),
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
            options[CONF_LOADS] = [l for l in loads if l[LOAD_SWITCH] not in remove]
            return self.async_create_entry(data=options)
        choices = [
            selector.SelectOptionDict(
                value=l[LOAD_SWITCH], label=f"{l[LOAD_NAME]} ({l[LOAD_SWITCH]})"
            )
            for l in loads
        ]
        schema = vol.Schema(
            {
                vol.Required("loads"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="remove_load", data_schema=schema)

    async def async_step_add_interlock(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Zwei Verbraucher gegeneinander verriegeln."""
        errors: dict[str, str] = {}
        options = self._options()
        if user_input is not None:
            if user_input[LOCK_A] == user_input[LOCK_B]:
                errors["base"] = "same_entity"
            else:
                pair = {LOCK_A: user_input[LOCK_A], LOCK_B: user_input[LOCK_B]}
                options[CONF_INTERLOCKS] = [*options.get(CONF_INTERLOCKS, []), pair]
                return self.async_create_entry(data=options)
        entity = selector.EntitySelector(selector.EntitySelectorConfig(domain=SWITCHABLE))
        schema = vol.Schema({vol.Required(LOCK_A): entity, vol.Required(LOCK_B): entity})
        return self.async_show_form(step_id="add_interlock", data_schema=schema, errors=errors)

    async def async_step_remove_interlock(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verriegelung entfernen."""
        options = self._options()
        locks: list[dict[str, str]] = list(options.get(CONF_INTERLOCKS, []))
        if not locks:
            return self.async_abort(reason="no_interlocks")
        if user_input is not None:
            remove = {int(i) for i in user_input["interlocks"]}
            options[CONF_INTERLOCKS] = [l for i, l in enumerate(locks) if i not in remove]
            return self.async_create_entry(data=options)
        choices = [
            selector.SelectOptionDict(value=str(i), label=f"{l[LOCK_A]} ↔ {l[LOCK_B]}")
            for i, l in enumerate(locks)
        ]
        schema = vol.Schema(
            {
                vol.Required("interlocks"): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=choices, multiple=True)
                )
            }
        )
        return self.async_show_form(step_id="remove_interlock", data_schema=schema)

    async def async_step_sources(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Quellen und Grenzen ändern."""
        options = self._options()
        if user_input is not None:
            for key in (CONF_LANDSTROM, CONF_V2L, CONF_BLUETTI_SOC):
                options[key] = user_input.get(key)
            options.update(
                {
                    k: v
                    for k, v in user_input.items()
                    if k not in (CONF_LANDSTROM, CONF_V2L, CONF_BLUETTI_SOC)
                }
            )
            return self.async_create_entry(data=options)
        current = {**self.config_entry.data, **options}
        return self.async_show_form(step_id="sources", data_schema=_sources_schema(current))
