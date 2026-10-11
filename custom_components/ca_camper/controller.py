"""Laufzeit-Controller: liest Zustände und berechnet die Leistungsbilanz.

Der Controller schaltet nichts. Er beobachtet die zugeordneten Entitäten und
stellt Quellen, Busleistungen, Grenze und Reserve für die Entitäten bereit.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_GENERATOR_MIN_SOC,
    CONF_GENERATOR_SOC,
    CONF_LANDSTROM,
    CONF_LIMIT_GENERATOR,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_V2L,
    DEFAULT_GENERATOR_MIN_SOC,
    DEFAULT_LIMIT_GENERATOR,
    DEFAULT_LIMIT_LANDSTROM,
    DEFAULT_LIMIT_V2L,
    LOAD_BUS,
    LOAD_NOMINAL,
    LOAD_POWER,
    LOAD_SWITCH,
    ON_STATES,
)
from .logic import (
    Balance,
    Bus,
    Limits,
    Load,
    compute_balance,
    generator_available,
    resolve_sources,
)


class CamperController:
    """Hält Konfiguration und aktuelle Bilanz für alle Entitäten der Integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        cfg: dict[str, Any] = {**entry.data, **entry.options}
        self._landstrom: str | None = cfg.get(CONF_LANDSTROM)
        self._v2l: str | None = cfg.get(CONF_V2L)
        self._generator_soc: str | None = cfg.get(CONF_GENERATOR_SOC)
        self._min_soc = float(cfg.get(CONF_GENERATOR_MIN_SOC, DEFAULT_GENERATOR_MIN_SOC))
        self.limits = Limits(
            landstrom_w=float(cfg.get(CONF_LIMIT_LANDSTROM, DEFAULT_LIMIT_LANDSTROM)),
            v2l_w=float(cfg.get(CONF_LIMIT_V2L, DEFAULT_LIMIT_V2L)),
            generator_w=float(cfg.get(CONF_LIMIT_GENERATOR, DEFAULT_LIMIT_GENERATOR)),
        )
        self.loads_cfg: list[dict[str, Any]] = list(entry.options.get(CONF_LOADS, []))
        self.balance: Balance | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[CALLBACK_TYPE] = []

    @callback
    def async_start(self) -> None:
        """Zustandsänderungen der zugeordneten Entitäten abonnieren."""
        watched = {e for e in (self._landstrom, self._v2l, self._generator_soc) if e}
        for load in self.loads_cfg:
            watched.add(load[LOAD_SWITCH])
            if load.get(LOAD_POWER):
                watched.add(load[LOAD_POWER])
        if watched:
            self._unsub.append(
                async_track_state_change_event(self.hass, sorted(watched), self._on_state_change)
            )
        self._recompute()

    @callback
    def async_stop(self) -> None:
        """Abos beenden."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Entität für Aktualisierungen registrieren."""
        self._listeners.append(update)

        @callback
        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    def _is_on(self, entity_id: str | None) -> bool:
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state in ON_STATES

    def _number(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _loads(self) -> list[Load]:
        loads: list[Load] = []
        for cfg in self.loads_cfg:
            is_on = self._is_on(cfg[LOAD_SWITCH])
            measured = self._number(cfg.get(LOAD_POWER))
            power = measured if measured is not None else float(cfg.get(LOAD_NOMINAL, 0))
            loads.append(
                Load(
                    load_id=cfg[LOAD_SWITCH],
                    bus=Bus(cfg[LOAD_BUS]),
                    is_on=is_on,
                    power_w=power if is_on else 0.0,
                )
            )
        return loads

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._recompute()

    @callback
    def _recompute(self) -> None:
        sources = resolve_sources(
            landstrom=self._is_on(self._landstrom),
            v2l=self._is_on(self._v2l),
            generator_ok=generator_available(self._number(self._generator_soc), self._min_soc),
        )
        self.balance = compute_balance(sources, self._loads(), self.limits)
        for update in list(self._listeners):
            update()
