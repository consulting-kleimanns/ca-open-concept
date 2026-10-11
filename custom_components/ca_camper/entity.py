"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import CamperController


class CamperEntity(Entity):
    """Basisentität, aktualisiert sich bei jeder Neuberechnung des Controllers."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: CamperController, key: str) -> None:
        self.controller = controller
        self._attr_translation_key = key
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name="CA Camper",
            manufacturer="CA Camping – Open Concept",
            model="Energiemanager",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Bei Controller-Änderungen neu schreiben."""
        await super().async_added_to_hass()
        self.async_on_remove(self.controller.async_add_listener(self.async_write_ha_state))
