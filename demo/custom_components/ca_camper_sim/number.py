"""Ziel- und Mindest-Ladestand der Fahrzeugbatterie."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity


async def async_setup_entry(hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    add(
        [
            Ladestand(hub, "soll_ladestand", "Ziel-Ladestand", "mdi:battery-charging-80", 50, 100),
            Ladestand(hub, "mindest_ladestand", "Mindest-Ladestand", "mdi:battery-10", 10, 50),
        ]
    )


class Ladestand(SimEntity, NumberEntity):
    """Grenze für Laden bzw. V2L."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 5
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub, key: str, name: str, icon: str, lo: float, hi: float) -> None:
        super().__init__(hub, "number", key, name, icon)
        self._key = key
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi

    @property
    def native_value(self) -> float:
        return getattr(self.m.s, self._key)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.m.s, self._key, float(value))
        self.hub.async_update()
