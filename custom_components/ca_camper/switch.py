"""Schalter: Lastmanagement und Verriegelung ein-/ausschalten."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import CamperConfigEntry
from .entity import CamperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CamperConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Schalter anlegen."""
    controller = entry.runtime_data
    async_add_entities(
        [ControlSwitch(controller, "load_management"), ControlSwitch(controller, "interlock")]
    )


class ControlSwitch(CamperEntity, SwitchEntity, RestoreEntity):
    """Steuerschalter der Integration; Zustand bleibt über Neustarts erhalten."""

    _attr_entity_category = EntityCategory.CONFIG

    async def async_added_to_hass(self) -> None:
        """Letzten Zustand wiederherstellen (Standard: an)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "off":
            self.controller.async_set_switch(self._attr_translation_key, False)

    @property
    def is_on(self) -> bool:
        """Aktiv?"""
        if self._attr_translation_key == "load_management":
            return self.controller.load_management_enabled
        return self.controller.interlock_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Einschalten."""
        self.controller.async_set_switch(self._attr_translation_key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ausschalten."""
        self.controller.async_set_switch(self._attr_translation_key, False)
