"""Zustände für ca_camper (Quellen, feste Verbraucher) und das Fahrzeug."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity
from .model import CamperModel


@dataclass(frozen=True)
class Zustand:
    key: str
    name: str
    value: Callable[[CamperModel], bool]
    icon: str | None = None
    device_class: BinarySensorDeviceClass | None = None


ZUSTAENDE = (
    Zustand(
        "landstrom",
        "Landstrom",
        lambda m: m.landstrom,
        "mdi:power-plug",
        BinarySensorDeviceClass.POWER,
    ),
    Zustand("v2l", "V2L", lambda m: m.v2l, "mdi:car-electric", BinarySensorDeviceClass.POWER),
    Zustand("kochfeld_an", "Kochfeld", lambda m: m.s.kochen_min > 0, "mdi:stove"),
    Zustand("dusche_an", "Dusche", lambda m: m.s.duschen_min > 0, "mdi:shower"),
    Zustand("heizung_laeuft", "Heizung läuft", lambda m: m.last.heizung_w > 0, "mdi:radiator"),
    Zustand(
        "infrarot_laeuft", "Infrarotheizung läuft", lambda m: m.last.infrarot_w > 0, "mdi:heat-wave"
    ),
    Zustand(
        "bewegung_kueche",
        "Bewegung Küche",
        lambda m: m.s.bewegung_min > 0,
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    Zustand(
        "klima_fahrerhaus",
        "Klima aktiv",
        lambda m: m.s.klima_fahrerhaus_min > 0,
        "mdi:air-conditioner",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback
) -> None:
    hub = entry.runtime_data
    add([SimBinary(hub, z) for z in ZUSTAENDE])


class SimBinary(SimEntity, BinarySensorEntity):
    """Ein Ein/Aus-Zustand der Simulation."""

    def __init__(self, hub, z: Zustand) -> None:
        super().__init__(hub, "binary_sensor", z.key, z.name, z.icon)
        self._z = z
        self._attr_device_class = z.device_class

    @property
    def is_on(self) -> bool:
        return self._z.value(self.m)
