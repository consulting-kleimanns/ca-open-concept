"""230-V-Kreise (je ein Shelly im Fahrzeug) und die Automatik des Küchenlichts."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity

KREISE = {
    "ac_03_generator_1": ("Generator 1", "mdi:generator-portable"),
    "ac_03_generator_2": ("Generator 2", "mdi:generator-portable"),
    "ac_04_reserve_1": ("Reserve 1", "mdi:power-socket-de"),
    "ac_04_reserve_2": ("Reserve 2", "mdi:power-socket-de"),
    "ac_02_boiler_heizstab": ("Boiler-Heizstab", "mdi:water-boiler"),
    "ac_07_steckdose_heck": ("Steckdose Heck", "mdi:power-socket-de"),
    "ac_08_steckdose_trennwand": ("Steckdose Trennwand", "mdi:power-socket-de"),
    "reserve_3": ("Reserve 3", "mdi:power-plug-outline"),
    "reserve_4": ("Reserve 4", "mdi:power-plug-outline"),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback
) -> None:
    hub = entry.runtime_data
    add([KreisSwitch(hub, key, *meta) for key, meta in KREISE.items()] + [KuechenAutomatik(hub)])


class KreisSwitch(SimEntity, SwitchEntity):
    """Ein 230-V-Abgang."""

    def __init__(self, hub, key: str, name: str, icon: str) -> None:
        super().__init__(hub, "switch", key, name, icon)
        self._key = key

    @property
    def is_on(self) -> bool:
        return self.m.s.circuits[self._key]

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.m.s.circuits[self._key] = True
        self.hub.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.m.s.circuits[self._key] = False
        self.hub.async_update()


class KuechenAutomatik(SimEntity, SwitchEntity):
    """Küchenlicht unter den Oberschränken per Bewegungsmelder."""

    def __init__(self, hub) -> None:
        super().__init__(
            hub, "switch", "kuechenlicht_automatik", "Küchenlicht Automatik", "mdi:motion-sensor"
        )

    @property
    def is_on(self) -> bool:
        return self.m.s.kuechenlicht_auto

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.m.s.kuechenlicht_auto = True
        self.hub.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.m.s.kuechenlicht_auto = False
        self.hub.async_update()
