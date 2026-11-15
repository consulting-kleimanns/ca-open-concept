"""Basisklasse: feste Entity-IDs laut Entity-Vertrag, ein gemeinsames Gerät."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .hub import SimHub


class SimEntity(Entity):
    """Entität der Simulation mit fester Entity-ID (``<domain>.<object_id>``)."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, hub: SimHub, domain: str, object_id: str, name: str, icon: str | None = None) -> None:
        self.hub = hub
        self.entity_id = f"{domain}.{object_id}"
        self._attr_unique_id = f"{DOMAIN}_{domain}_{object_id}"
        self._attr_name = name
        if icon:
            self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "camper")},
            name="Mein Master (Simulation)",
            manufacturer="CA Camping",
            model="Renault Master E-Tech – Demo",
        )

    @property
    def m(self):  # noqa: ANN201 – Kurzform für das Modell
        return self.hub.model

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.async_add_listener(self.async_write_ha_state))
