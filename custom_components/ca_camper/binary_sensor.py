"""Binärsensoren: Überlast (Warnung) und Freigabe je Verbraucher „nur mit Reserve“."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CamperConfigEntry
from .const import LOAD_NAME, LOAD_SWITCH
from .controller import CamperController
from .entity import CamperEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CamperConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Binärsensoren anlegen."""
    controller = entry.runtime_data
    entities: list[BinarySensorEntity] = [OverloadSensor(controller, "ueberlast")]
    entities += [
        ReleaseSensor(controller, cfg[LOAD_SWITCH], cfg[LOAD_NAME])
        for cfg in controller.flexible_loads
    ]
    async_add_entities(entities)


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


class ReleaseSensor(CamperEntity, BinarySensorEntity):
    """An, solange die speisende Quelle den Verbraucher zusätzlich trägt."""

    def __init__(self, controller: CamperController, switch_entity: str, name: str) -> None:
        super().__init__(controller, f"freigabe_{switch_entity}", "freigabe", {"name": name})
        self._switch = switch_entity

    @property
    def is_on(self) -> bool | None:
        """Freigegeben?"""
        if self.controller.balance is None:
            return None
        return self.controller.releases.get(self._switch, False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Geschalteter Verbraucher und ob er von der Freigabesteuerung pausiert ist."""
        return {
            "verbraucher": self._switch,
            "pausiert": self._switch in self.controller.paused,
        }
