"""Binärsensor: Überlast der speisenden Quelle."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CamperConfigEntry
from .entity import CamperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CamperConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Binärsensor anlegen."""
    async_add_entities([OverloadSensor(entry.runtime_data, "ueberlast")])


class OverloadSensor(CamperEntity, BinarySensorEntity):
    """An, solange die Last die Grenze der aktiven Quelle überschreitet."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool | None:
        """Überlast?"""
        balance = self.controller.balance
        return balance.overload if balance else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Verbraucher, die gerade keine Quelle haben."""
        balance = self.controller.balance
        return {"spannungslose_verbraucher": balance.unpowered_loads if balance else []}
