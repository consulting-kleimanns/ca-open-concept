"""Schalter „Freigabesteuerung“: pausiert Verbraucher „nur mit Reserve“ bei fehlender Reserve."""

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
    async_add_entities([AutoReleaseSwitch(entry.runtime_data, "freigabesteuerung")])


class AutoReleaseSwitch(CamperEntity, SwitchEntity, RestoreEntity):
    """Ein: Reserve-Verbraucher werden automatisch pausiert und wieder eingeschaltet."""

    _attr_entity_category = EntityCategory.CONFIG

    async def async_added_to_hass(self) -> None:
        """Letzten Zustand wiederherstellen (Vorgabe: ein)."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "off":
            self.controller.async_set_auto(False)

    @property
    def is_on(self) -> bool:
        """Freigabesteuerung aktiv?"""
        return self.controller.auto_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Einschalten."""
        self.controller.async_set_auto(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Ausschalten."""
        self.controller.async_set_auto(False)
