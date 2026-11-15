"""Laufzeit der Simulation: Modell, Takt, Speicherung, Benachrichtigung der Entitäten."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import DEFAULT_ZEITRAFFER, DOMAIN, SAVE_EVERY_TICKS, TICK_SECONDS, ZEITRAFFER
from .model import Boiler, CamperModel, Climate, Standort, State
from .umgebung import async_suche

_LOGGER = logging.getLogger(__name__)

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
        # Umgebung des Standorts (Ergebnis der letzten Suche) und laufende Suche
        self.umgebung: dict[str, Any] = {}
        self.umgebung_status = "bereit"
        self._suche: asyncio.Task | None = None

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
        self.umgebung = data.get("umgebung", {})

    async def async_save(self) -> None:
        """Zustand sichern."""
        await self._store.async_save(
            {"state": asdict(self.model.s), "zeitraffer": self.zeitraffer, "umgebung": self.umgebung}
        )

    # --- Takt -----------------------------------------------------------------------------------

    @callback
    def async_start(self) -> None:
        """Takt starten."""
        self.model.tick(0)
        if self.model.s.ort and self.umgebung.get("ort") != self.model.s.ort:
            self.async_set_ort(self.model.s.ort)
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

    # --- Umgebung -----------------------------------------------------------------------------

    @callback
    def async_set_ort(self, ort: str) -> None:
        """Neuen Standort übernehmen und die Umgebung im Hintergrund suchen."""
        self.model.s.ort = ort.strip()
        if self._suche and not self._suche.done():
            self._suche.cancel()
        if not self.model.s.ort:
            self.umgebung, self.umgebung_status = {}, "bereit"
        else:
            self.umgebung_status = "sucht"
            self._suche = self.hass.async_create_background_task(
                self._async_suche(self.model.s.ort), f"{DOMAIN}_umgebung"
            )
        self.async_update()

    async def _async_suche(self, ort: str) -> None:
        """Sucht die Umgebung; bei überlasteten OSM-Servern mit wachsender Pause erneut."""
        for versuch, pause in enumerate((0, 30, 90, 300, 900)):
            if pause:
                self.umgebung_status = "wartet"
                self.async_update()
                await asyncio.sleep(pause)
                self.umgebung_status = "sucht"
                self.async_update()
            try:
                res = await async_suche(async_get_clientsession(self.hass), ort)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 – Netzfehler sichtbar im Status
                _LOGGER.info(
                    "Umgebungssuche für %s, Versuch %s: %s", ort, versuch + 1, repr(err)[:160]
                )
                continue
            res["stand"] = datetime.now().isoformat(timespec="minutes")
            self.umgebung = res
            self.umgebung_status = "ok" if res.get("gefunden") else "nicht_gefunden"
            await self.async_save()
            self.async_update()
            return
        _LOGGER.warning("Umgebungssuche für %s aufgegeben – OpenStreetMap nicht erreichbar", ort)
        self.umgebung_status = "fehler"
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
