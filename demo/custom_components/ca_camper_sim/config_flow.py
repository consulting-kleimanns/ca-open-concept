"""Einrichtung ohne Eingaben – es gibt genau eine Simulation je Instanz."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class SimConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Flow der Simulation."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ein Klick genügt."""
        if user_input is not None:
            return self.async_create_entry(title="CA Camper Simulation", data={})
        return self.async_show_form(step_id="user")
