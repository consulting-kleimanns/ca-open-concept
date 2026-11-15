"""Heizung (Truma, Stufen Eco/High) und Wandthermostat (Infrarotheizung)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback
) -> None:
    hub = entry.runtime_data
    add(
        [
            Heizung(hub, "heizung", "Truma Heizung", True),
            Heizung(hub, "wandthermostat", "Wandthermostat", False),
        ]
    )


class Heizung(SimEntity, ClimateEntity):
    """Heizkreis mit Zieltemperatur."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.5

    def __init__(self, hub, key: str, name: str, presets: bool) -> None:
        super().__init__(hub, "climate", key, name, "mdi:radiator" if presets else "mdi:thermostat")
        self._key = key
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if presets:
            features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = ["eco", "high"]
        self._attr_supported_features = features

    @property
    def _c(self):
        return getattr(self.m.s, self._key)

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self._c.on else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self._c.on:
            return HVACAction.OFF
        return HVACAction.HEATING if self.m.s.innen < self._c.target else HVACAction.IDLE

    @property
    def current_temperature(self) -> float:
        return round(self.m.s.innen, 1)

    @property
    def target_temperature(self) -> float:
        return self._c.target

    @property
    def preset_mode(self) -> str | None:
        return self._c.preset if self._key == "heizung" else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._c.on = hvac_mode == HVACMode.HEAT
        self.hub.async_update()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._c.target = float(temp)
            self.hub.async_update()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._c.preset = preset_mode
        self.hub.async_update()
