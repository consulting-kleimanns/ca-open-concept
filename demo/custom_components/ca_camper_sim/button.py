"""Fahrzeugfunktionen (Vorklimatisieren, Hupe …) und „Im Camper ausprobieren“."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity
from .model import CamperModel


@dataclass(frozen=True)
class Aktion:
    key: str
    name: str
    icon: str
    run: Callable[[CamperModel], object]


def _set(attr: str, value: float) -> Callable[[CamperModel], None]:
    return lambda m: setattr(m.s, attr, value)


AKTIONEN = (
    Aktion("vorklimatisieren", "Vorklimatisieren", "mdi:fan", _set("klima_fahrerhaus_min", 15)),
    Aktion("hupe", "Hupe", "mdi:bullhorn", _set("hupe_min", 0.2)),
    Aktion("lichthupe", "Lichthupe", "mdi:car-light-high", _set("lichthupe_min", 0.2)),
    Aktion("laden_starten", "Laden starten", "mdi:play-circle", lambda m: m.laden_starten()),
    Aktion("sim_einsteigen", "Einsteigen (Demo)", "mdi:door-open", lambda m: m.einsteigen()),
    Aktion("sim_kochen", "Kochen mit 2 Feldern (Demo)", "mdi:pot-steam", lambda m: m.kochen()),
    Aktion("sim_duschen", "Duschen (Demo)", "mdi:shower", lambda m: m.duschen()),
    Aktion(
        "sim_kueche_betreten",
        "In die Küche gehen (Demo)",
        "mdi:walk",
        lambda m: m.kueche_betreten(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback
) -> None:
    hub = entry.runtime_data
    add([AktionButton(hub, a) for a in AKTIONEN])


class AktionButton(SimEntity, ButtonEntity):
    """Einmalige Aktion."""

    def __init__(self, hub, aktion: Aktion) -> None:
        super().__init__(hub, "button", aktion.key, aktion.name, aktion.icon)
        self._run = aktion.run

    async def async_press(self) -> None:
        self._run(self.m)
        self.hub.async_update()
