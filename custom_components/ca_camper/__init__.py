"""CA Camper Energiemanager – Open-Concept-Logik für den vollelektrischen Camper.

Die Integration misst und zeigt an. Schalten darf sie nur Verbraucher „nur mit Reserve“
(z. B. Boiler-Heizstab, Laden des Solargenerators). Sie nutzt vorhandene Entitäten
(z. B. Shelly-Schalter und -Leistungsmessung, Ladestand des Solargenerators,
Landstrom-/V2L-Erkennung) und bildet darauf die Vorrangschaltungen und die
Leistungsbilanz je Bus aus dem Elektroplan ab.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .controller import CamperController

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

type CamperConfigEntry = ConfigEntry[CamperController]


async def async_setup_entry(hass: HomeAssistant, entry: CamperConfigEntry) -> bool:
    """Integration aus einem Config Entry einrichten."""
    controller = CamperController(hass, entry)
    entry.runtime_data = controller
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    controller.async_start()
    entry.async_on_unload(controller.async_stop)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CamperConfigEntry) -> bool:
    """Integration entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: CamperConfigEntry) -> None:
    """Nach Änderung der Optionen neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)
