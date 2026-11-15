"""Boiler-Betriebsart sowie die Demo-Einstellungen Standort und Zeitraffer."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .const import ZEITRAFFER
from .entity import SimEntity
from .model import Boiler, Standort

STANDORT_LABEL = {
    Standort.CAMPINGPLATZ_16A: "Campingplatz (16 A)",
    Standort.CAMPINGPLATZ_10A: "Campingplatz (10 A)",
    Standort.FREI_V2L: "Frei stehend – Strom aus dem Fahrzeug",
    Standort.ZUHAUSE_WALLBOX: "Zu Hause an der Wallbox",
}


async def async_setup_entry(hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    add([BoilerSelect(hub), StandortSelect(hub), ZeitrafferSelect(hub)])


class BoilerSelect(SimEntity, SelectEntity):
    """Boiler: Aus, Eco (ca. 45 °C), High (60 °C), Boost (60 °C, sofort)."""

    _attr_options = [b.value for b in Boiler]

    def __init__(self, hub) -> None:
        super().__init__(hub, "select", "boiler", "Boiler", "mdi:water-boiler")

    @property
    def current_option(self) -> str:
        return self.m.s.boiler.value

    async def async_select_option(self, option: str) -> None:
        self.m.s.boiler = Boiler(option)
        self.hub.async_update()


class StandortSelect(SimEntity, SelectEntity):
    """Demo: Stromsituation am Standort."""

    _attr_options = list(STANDORT_LABEL.values())

    def __init__(self, hub) -> None:
        super().__init__(hub, "select", "sim_strom_vor_ort", "Strom vor Ort (Demo)", "mdi:map-marker-radius")

    @property
    def current_option(self) -> str:
        return STANDORT_LABEL[self.m.s.standort]

    async def async_select_option(self, option: str) -> None:
        standort = next(k for k, v in STANDORT_LABEL.items() if v == option)
        self.m.set_standort(standort)
        self.hub.async_update()


class ZeitrafferSelect(SimEntity, SelectEntity):
    """Demo: Zeitraffer der Simulation."""

    _attr_options = list(ZEITRAFFER)
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub) -> None:
        super().__init__(hub, "select", "sim_zeitraffer", "Zeitraffer (Demo)", "mdi:fast-forward")

    @property
    def current_option(self) -> str:
        return self.hub.zeitraffer

    async def async_select_option(self, option: str) -> None:
        self.hub.zeitraffer = option
        self.hub.async_update()
