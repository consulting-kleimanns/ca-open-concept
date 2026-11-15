"""LED-Leisten: Heck links/rechts und Dusche dimmbar, Küche per Bewegungsmelder."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity

LEISTEN = {
    "heck_links": "Heck links",
    "heck_rechts": "Heck rechts",
    "dusche": "Dusche",
}


async def async_setup_entry(hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    add([Leiste(hub, key, name) for key, name in LEISTEN.items()] + [Kuechenlicht(hub)])


class Leiste(SimEntity, LightEntity):
    """Dimmbare LED-Leiste (Shelly Plus RGBW PM, ein Kanal)."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hub, key: str, name: str) -> None:
        super().__init__(hub, "light", key, name, "mdi:led-strip-variant")
        self._key = key

    @property
    def is_on(self) -> bool:
        return self.m.s.lights[self._key] > 0

    @property
    def brightness(self) -> int:
        return self.m.s.lights[self._key]

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.m.s.lights[self._key] = int(kwargs.get(ATTR_BRIGHTNESS, self.m.s.lights[self._key] or 178))
        self.hub.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.m.s.lights[self._key] = 0
        self.hub.async_update()


class Kuechenlicht(SimEntity, LightEntity):
    """Licht unter den Oberschränken – schaltet per Bewegung, lässt sich aber auch direkt bedienen."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, hub) -> None:
        super().__init__(hub, "light", "kueche", "Küche", "mdi:led-strip-variant")

    @property
    def is_on(self) -> bool:
        return self.m.kuechenlicht

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.m.s.kuechenlicht_auto = True
        self.m.kueche_betreten()
        self.hub.async_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.m.s.bewegung_min = 0
        self.hub.async_update()
