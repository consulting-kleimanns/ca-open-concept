"""Laufzeit-Controller: liest Zustände, wendet die Logik an, schaltet Verbraucher."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import (
    CONF_BLUETTI_MIN_SOC,
    CONF_BLUETTI_SOC,
    CONF_INTERLOCKS,
    CONF_LANDSTROM,
    CONF_LIMIT_BLUETTI,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_SHED_DELAY,
    CONF_V2L,
    DEFAULT_BLUETTI_MIN_SOC,
    DEFAULT_LIMIT_BLUETTI,
    DEFAULT_LIMIT_LANDSTROM,
    DEFAULT_LIMIT_V2L,
    DEFAULT_SHED_DELAY,
    EVENT_INTERLOCK,
    EVENT_LOAD_SHED,
    LOAD_BUS,
    LOAD_ID,
    LOAD_NAME,
    LOAD_NOMINAL,
    LOAD_POWER,
    LOAD_PRIORITY,
    LOAD_SHEDDABLE,
    LOAD_SWITCH,
    LOCK_A,
    LOCK_B,
    ON_STATES,
)
from .logic import (
    Balance,
    Bus,
    Limits,
    Load,
    bluetti_available,
    compute_balance,
    interlock_partners,
    resolve_sources,
    select_loads_to_shed,
)

_LOGGER = logging.getLogger(__name__)


class CamperController:
    """Hält Konfiguration und aktuellen Zustand für alle Entitäten der Integration."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        cfg: dict[str, Any] = {**entry.data, **entry.options}
        self._landstrom: str | None = cfg.get(CONF_LANDSTROM)
        self._v2l: str | None = cfg.get(CONF_V2L)
        self._bluetti_soc: str | None = cfg.get(CONF_BLUETTI_SOC)
        self._min_soc = float(cfg.get(CONF_BLUETTI_MIN_SOC, DEFAULT_BLUETTI_MIN_SOC))
        self.limits = Limits(
            landstrom_w=float(cfg.get(CONF_LIMIT_LANDSTROM, DEFAULT_LIMIT_LANDSTROM)),
            v2l_w=float(cfg.get(CONF_LIMIT_V2L, DEFAULT_LIMIT_V2L)),
            bluetti_w=float(cfg.get(CONF_LIMIT_BLUETTI, DEFAULT_LIMIT_BLUETTI)),
        )
        self._shed_delay = float(cfg.get(CONF_SHED_DELAY, DEFAULT_SHED_DELAY))
        self.loads_cfg: list[dict[str, Any]] = list(entry.options.get(CONF_LOADS, []))
        self.interlocks: list[tuple[str, str]] = [
            (i[LOCK_A], i[LOCK_B]) for i in entry.options.get(CONF_INTERLOCKS, [])
        ]

        self.load_management_enabled = True
        self.interlock_enabled = True
        self.balance: Balance | None = None
        self.last_action: str | None = None

        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[CALLBACK_TYPE] = []
        self._shed_timer: CALLBACK_TYPE | None = None

    # ---------------------------------------------------------------- Lebenszyklus
    @callback
    def async_start(self) -> None:
        """Zustandsänderungen der zugeordneten Entitäten abonnieren."""
        watched = {e for e in (self._landstrom, self._v2l, self._bluetti_soc) if e}
        for load in self.loads_cfg:
            watched.add(load[LOAD_SWITCH])
            if load.get(LOAD_POWER):
                watched.add(load[LOAD_POWER])
        for a, b in self.interlocks:
            watched.update((a, b))
        if watched:
            self._unsub.append(
                async_track_state_change_event(self.hass, sorted(watched), self._on_state_change)
            )
        self._recompute()

    @callback
    def async_stop(self) -> None:
        """Abos und Timer beenden."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        self._cancel_shed_timer()

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Entität für Aktualisierungen registrieren."""
        self._listeners.append(update)

        @callback
        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    @callback
    def async_set_switch(self, key: str, value: bool) -> None:
        """Steuer-Schalter der Integration (Lastmanagement/Verriegelung) setzen."""
        if key == "load_management":
            self.load_management_enabled = value
        elif key == "interlock":
            self.interlock_enabled = value
        self._recompute()

    # ---------------------------------------------------------------- Zustände lesen
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
                    priority=int(cfg[LOAD_PRIORITY]),
                    is_on=is_on,
                    power_w=power if is_on else 0.0,
                    sheddable=bool(cfg.get(LOAD_SHEDDABLE, True)),
                )
            )
        return loads

    def load_name(self, entity_id: str) -> str:
        """Anzeigename eines Verbrauchers."""
        for cfg in self.loads_cfg:
            if cfg[LOAD_SWITCH] == entity_id:
                return cfg.get(LOAD_NAME) or cfg.get(LOAD_ID) or entity_id
        state = self.hass.states.get(entity_id)
        return state.name if state else entity_id

    # ---------------------------------------------------------------- Reaktion
    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        old, new = event.data["old_state"], event.data["new_state"]
        turned_on = (
            new is not None
            and new.state in ON_STATES
            and (old is None or old.state not in ON_STATES)
        )
        if turned_on and self.interlock_enabled and self.interlocks:
            self._apply_interlock(entity_id)
        self._recompute()

    @callback
    def _apply_interlock(self, turned_on: str) -> None:
        partners = interlock_partners(
            turned_on,
            self.interlocks,
            {e: self._is_on(e) for pair in self.interlocks for e in pair},
        )
        for partner in partners:
            _LOGGER.info(
                "Verriegelung: %s eingeschaltet, %s wird ausgeschaltet", turned_on, partner
            )
            self.last_action = f"Verriegelung: {self.load_name(partner)} aus"
            self._turn_off(partner)
            self.hass.bus.async_fire(
                EVENT_INTERLOCK, {"turned_on": turned_on, "turned_off": partner}
            )

    @callback
    def _recompute(self) -> None:
        sources = resolve_sources(
            landstrom=self._is_on(self._landstrom),
            v2l=self._is_on(self._v2l),
            bluetti_ok=bluetti_available(self._number(self._bluetti_soc), self._min_soc),
        )
        self.balance = compute_balance(sources, self._loads(), self.limits)

        if self.balance.overload and self.load_management_enabled:
            if self._shed_timer is None:
                self._shed_timer = async_call_later(
                    self.hass, self._shed_delay, self._shed_if_still_overloaded
                )
        else:
            self._cancel_shed_timer()

        for update in list(self._listeners):
            update()

    @callback
    def _shed_if_still_overloaded(self, _now: Any) -> None:
        self._shed_timer = None
        if not self.load_management_enabled:
            return
        sources = resolve_sources(
            landstrom=self._is_on(self._landstrom),
            v2l=self._is_on(self._v2l),
            bluetti_ok=bluetti_available(self._number(self._bluetti_soc), self._min_soc),
        )
        to_shed = select_loads_to_shed(sources, self._loads(), self.limits)
        if not to_shed:
            return
        names = ", ".join(self.load_name(e) for e in to_shed)
        _LOGGER.warning("Lastabwurf wegen Überlast: %s", names)
        self.last_action = f"Lastabwurf: {names}"
        for entity_id in to_shed:
            self._turn_off(entity_id)
        self.hass.bus.async_fire(
            EVENT_LOAD_SHED,
            {"entities": to_shed, "limit_w": self.balance.limit_w if self.balance else None},
        )
        self._recompute()

    @callback
    def _turn_off(self, entity_id: str) -> None:
        self.hass.async_create_task(
            self.hass.services.async_call(
                "homeassistant", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=False
            )
        )

    @callback
    def _cancel_shed_timer(self) -> None:
        if self._shed_timer is not None:
            self._shed_timer()
            self._shed_timer = None
