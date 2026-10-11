"""Laufzeit-Controller: liest Zustände, berechnet Bilanz und Freigaben.

Feste Verbraucher werden nie geschaltet. Nur Verbraucher „nur mit Reserve“ (z. B. Boiler-Heizstab,
Laden des Solargenerators) pausiert der Controller, wenn die Quelle sie nicht mehr trägt, und schaltet
sie wieder ein, sobald die Reserve stabil reicht – vorausgesetzt, die Freigabesteuerung ist aktiv.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event

from .const import (
    CONF_CHARGE_SWITCH,
    CONF_DELAY_OFF,
    CONF_DELAY_ON,
    CONF_GENERATOR_MIN_SOC,
    CONF_GENERATOR_SOC,
    CONF_LANDSTROM,
    CONF_LIMIT_GENERATOR,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_MARGIN,
    CONF_V2L,
    CONF_V2L_CHARGE_START,
    CONF_V2L_CHARGE_STOP,
    DEFAULT_DELAY_OFF,
    DEFAULT_DELAY_ON,
    DEFAULT_GENERATOR_MIN_SOC,
    DEFAULT_LIMIT_GENERATOR,
    DEFAULT_LIMIT_LANDSTROM,
    DEFAULT_LIMIT_V2L,
    DEFAULT_MARGIN,
    DEFAULT_V2L_CHARGE_START,
    DEFAULT_V2L_CHARGE_STOP,
    LOAD_BUS,
    LOAD_FLEXIBLE,
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
    Source,
    compute_balance,
    compute_releases,
    generator_available,
    resolve_sources,
    v2l_charge_needed,
)


class CamperController:
    """Hält Konfiguration, Bilanz und Freigaben für alle Entitäten der Integration."""

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
        self.margin_w = float(cfg.get(CONF_MARGIN, DEFAULT_MARGIN))
        self.delay_off = float(cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF))
        self.delay_on = float(cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON))
        self.charge_switch: str | None = cfg.get(CONF_CHARGE_SWITCH)
        self.v2l_start = float(cfg.get(CONF_V2L_CHARGE_START, DEFAULT_V2L_CHARGE_START))
        self.v2l_stop = float(cfg.get(CONF_V2L_CHARGE_STOP, DEFAULT_V2L_CHARGE_STOP))
        self.v2l_charge = False
        self.loads_cfg: list[dict[str, Any]] = list(entry.options.get(CONF_LOADS, []))
        self.balance: Balance | None = None
        self.releases: dict[str, bool] = {}
        self.paused: set[str] = set()
        self.auto_enabled = True
        self._timers: dict[str, CALLBACK_TYPE] = {}
        self._listeners: list[Callable[[], None]] = []
        self._unsub: list[CALLBACK_TYPE] = []

    @property
    def flexible_loads(self) -> list[dict[str, Any]]:
        """Konfigurierte Verbraucher „nur mit Reserve“."""
        return [cfg for cfg in self.loads_cfg if cfg.get(LOAD_FLEXIBLE)]

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
        """Abos und Timer beenden."""
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()
        self._cancel_all()

    @callback
    def async_add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        """Entität für Aktualisierungen registrieren."""
        self._listeners.append(update)

        @callback
        def _remove() -> None:
            self._listeners.remove(update)

        return _remove

    @callback
    def async_set_auto(self, enabled: bool) -> None:
        """Freigabesteuerung ein- oder ausschalten (Schalter-Entität)."""
        self.auto_enabled = enabled
        if not enabled:
            self._cancel_all()
            self.paused.clear()
        self._recompute()

    # --- Zustände lesen -------------------------------------------------------------------------

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
            nominal = float(cfg.get(LOAD_NOMINAL, 0))
            measured = self._number(cfg.get(LOAD_POWER))
            power = measured if measured is not None else nominal
            loads.append(
                Load(
                    load_id=cfg[LOAD_SWITCH],
                    bus=Bus(cfg[LOAD_BUS]),
                    is_on=is_on,
                    power_w=power if is_on else 0.0,
                    nominal_w=nominal,
                    flexible=bool(cfg.get(LOAD_FLEXIBLE)),
                )
            )
        return loads

    # --- Berechnung und Freigabesteuerung --------------------------------------------------------

    @callback
    def _on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._recompute()

    @callback
    def _recompute(self) -> None:
        soc = self._number(self._generator_soc)
        sources = resolve_sources(
            landstrom=self._is_on(self._landstrom),
            v2l=self._is_on(self._v2l),
            generator_ok=generator_available(soc, self._min_soc),
        )
        loads = self._loads()
        self.balance = compute_balance(sources, loads, self.limits)
        # Laden aus der Fahrzeugbatterie nur bei niedrigem Ladestand; Landstrom lädt jederzeit.
        self.v2l_charge = v2l_charge_needed(soc, self.v2l_start, self.v2l_stop, self.v2l_charge)
        blocked: frozenset[str] = frozenset()
        if self.charge_switch and sources.primaer is Source.V2L and not self.v2l_charge:
            blocked = frozenset({self.charge_switch})
        self.releases = compute_releases(
            sources, loads, self.limits, self.margin_w, blocked, frozenset(self.paused)
        )
        if self.auto_enabled:
            self._plan_actions()
        for update in list(self._listeners):
            update()

    @callback
    def _plan_actions(self) -> None:
        for cfg in self.flexible_loads:
            entity_id: str = cfg[LOAD_SWITCH]
            released = self.releases.get(entity_id, False)
            is_on = self._is_on(entity_id)
            if is_on and not released:
                self._schedule(entity_id, "off", self.delay_off)
            elif not is_on and released and entity_id in self.paused:
                self._schedule(entity_id, "on", self.delay_on)
            else:
                self._cancel(entity_id)

    @callback
    def _schedule(self, entity_id: str, action: str, delay: float) -> None:
        key = f"{entity_id}:{action}"
        other = f"{entity_id}:{'on' if action == 'off' else 'off'}"
        if other in self._timers:
            self._timers.pop(other)()
        if key in self._timers:
            return

        @callback
        def _fire(_now: datetime) -> None:
            self._timers.pop(key, None)
            self.hass.async_create_task(self._async_execute(entity_id, action))

        self._timers[key] = async_call_later(self.hass, delay, _fire)

    async def _async_execute(self, entity_id: str, action: str) -> None:
        """Nach Ablauf der Verzögerung erneut prüfen und schalten."""
        if not self.auto_enabled:
            return
        released = self.releases.get(entity_id, False)
        is_on = self._is_on(entity_id)
        if action == "off" and is_on and not released:
            self.paused.add(entity_id)
            await self._async_switch(entity_id, "turn_off")
        elif action == "on" and not is_on and released and entity_id in self.paused:
            self.paused.discard(entity_id)
            await self._async_switch(entity_id, "turn_on")
        for update in list(self._listeners):
            update()

    async def _async_switch(self, entity_id: str, service: str) -> None:
        domain = entity_id.split(".", 1)[0]
        await self.hass.services.async_call(
            domain, service, {ATTR_ENTITY_ID: entity_id}, blocking=True
        )

    @callback
    def _cancel(self, entity_id: str) -> None:
        for action in ("on", "off"):
            unsub = self._timers.pop(f"{entity_id}:{action}", None)
            if unsub:
                unsub()

    @callback
    def _cancel_all(self) -> None:
        for unsub in self._timers.values():
            unsub()
        self._timers.clear()
