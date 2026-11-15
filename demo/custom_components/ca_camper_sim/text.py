"""Standort als Ort oder PLZ – Grundlage für die Umgebungsvorschläge (im Fahrzeug: GPS)."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback
) -> None:
    add([Standort(entry.runtime_data)])


class Standort(SimEntity, TextEntity):
    """Ort oder PLZ, an dem der Camper in der Demo steht."""

    _attr_native_max = 80

    def __init__(self, hub) -> None:
        super().__init__(hub, "text", "standort", "Standort (Ort oder PLZ)", "mdi:map-marker")

    @property
    def native_value(self) -> str:
        return self.m.s.ort

    async def async_set_value(self, value: str) -> None:
        self.hub.async_set_ort(value)
