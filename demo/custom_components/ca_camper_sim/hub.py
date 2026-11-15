"""Laufzeit der Simulation: Modell, Takt, Speicherung, Benachrichtigung der Entitäten."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DEFAULT_ZEITRAFFER, DOMAIN, SAVE_EVERY_TICKS, TICK_SECONDS, ZEITRAFFER
from .model import Boiler, CamperModel, Climate, Standort, State

STORAGE_VERSION = 1


class SimHub:
    """Hält das Modell und taktet es."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self.model = CamperModel()
        self.zeitraffer = DEFAULT_ZEITRAFFER
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.state")
        self._listeners: list[Callable[[], None]] = []
        self._unsub: CALLBACK_TYPE | None = None
        self._ticks = 0

    # --- Persistenz -----------------------------------------------------------------------------

    async def async_load(self) -> None:
        """Gesicherten Zustand laden (bleibt über Neustarts und Logins erhalten)."""
        data = await self._store.async_load()
        if not data:
            return
        st = State()
        for key, value in data.get("state", {}).items():
            if not hasattr(st, key):
                continue
            if key in ("heizung", "wandthermostat"):
                value = Climate(**value)
            elif key == "standort":
                value = Standort(value)
            elif key == "boiler":
                value = Boiler(value)
            setattr(st, key, value)
        self.model.s = st
        self.zeitraffer = data.get("zeitraffer", DEFAULT_ZEITRAFFER)

    async def async_save(self) -> None:
        """Zustand sichern."""
        await self._store.async_save({"state": asdict(self.model.s), "zeitraffer": self.zeitraffer})

    # --- Takt -----------------------------------------------------------------------------------

    @callback
    def async_start(self) -> None:
        """Takt starten."""
        self.model.tick(0)
        self._unsub = async_track_time_interval(
            self.hass, self._tick, timedelta(seconds=TICK_SECONDS)
        )

    @callback
    def async_stop(self) -> None:
        """Takt stoppen."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    @callback
    def _tick(self, _now: Any) -> None:
        factor = ZEITRAFFER.get(self.zeitraffer, 1)
        self.model.tick(TICK_SECONDS / 60 * factor)
        self._ticks += 1
        if self._ticks % SAVE_EVERY_TICKS == 0:
            self.hass.async_create_task(self.async_save())
        self.async_update()

    # --- Entitäten ------------------------------------------------------------------------------

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Entität registrieren."""
        self._listeners.append(update)

        @callback
        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    @callback
    def async_update(self) -> None:
        """Nach einer Änderung neu rechnen und alle Entitäten aktualisieren."""
        self.model.last = self.model.snapshot()
        for update in list(self._listeners):
            update()
