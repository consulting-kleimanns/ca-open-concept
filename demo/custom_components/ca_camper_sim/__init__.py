"""CA Camper Simulation – bildet die Hardware eines CA-Campers für die Demo nach.

Stellt die Entitäten des Entity-Vertrags bereit (siehe demo/README.md). Die echte Integration
``ca_camper`` läuft unverändert darauf und schaltet wie im Fahrzeug die Verbraucher
„nur mit Reserve“.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .hub import SimHub

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

type SimConfigEntry = ConfigEntry[SimHub]


async def async_setup_entry(hass: HomeAssistant, entry: SimConfigEntry) -> bool:
    """Simulation starten."""
    hub = SimHub(hass)
    await hub.async_load()
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hub.async_start()
    entry.async_on_unload(hub.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SimConfigEntry) -> bool:
    """Simulation beenden."""
    await entry.runtime_data.async_save()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
