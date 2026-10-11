"""Reine Entscheidungslogik des CA-Camper-Energiemanagers (ohne Home-Assistant-Abhängigkeit).

Bildet den Open-Concept-Elektroplan ab:
- VS1: Landstrom vor Fahrzeug-V2L  -> Primärbus
- VS2: Primärbus vor Bluetti-Ausgang -> Komfortbus

Hängt der Komfortbus am Primärbus, teilen sich beide Busse die Grenze der aktiven Quelle.
Hängt er an der Bluetti, sind Verbraucher des Primärbusses spannungslos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Source(StrEnum):
    """Mögliche Einspeisungen."""

    LANDSTROM = "landstrom"
    V2L = "v2l"
    BLUETTI = "bluetti"
    KEINE = "keine"


class Bus(StrEnum):
    """230-V-Busse laut Elektroplan."""

    PRIMAER = "primaer"
    KOMFORT = "komfort"


@dataclass(frozen=True)
class Limits:
    """Dauerleistungsgrenzen der Quellen in Watt."""

    landstrom_w: float
    v2l_w: float
    bluetti_w: float

    def for_source(self, source: Source) -> float:
        """Grenze der Quelle; ohne Quelle 0 W."""
        return {
            Source.LANDSTROM: self.landstrom_w,
            Source.V2L: self.v2l_w,
            Source.BLUETTI: self.bluetti_w,
        }.get(source, 0.0)


@dataclass(frozen=True)
class Load:
    """Ein geschalteter Verbraucher (ein Shelly-Kanal)."""

    load_id: str
    bus: Bus
    priority: int  # 1 = wichtig, wird zuletzt abgeworfen; 10 = zuerst
    is_on: bool
    power_w: float  # gemessene oder nominale Leistung, wenn eingeschaltet
    sheddable: bool = True


@dataclass(frozen=True)
class SourceState:
    """Ergebnis der Vorrangschaltungen."""

    primaer: Source
    komfort: Source


@dataclass
class Balance:
    """Leistungsbilanz der aktiven Einspeisung(en)."""

    sources: SourceState
    power_primaer_w: float
    power_komfort_w: float
    limit_w: float
    load_w: float
    headroom_w: float
    overload: bool
    unpowered_loads: list[str] = field(default_factory=list)


def resolve_sources(landstrom: bool, v2l: bool, bluetti_ok: bool) -> SourceState:
    """Vorrangschaltungen VS1 und VS2 nachbilden."""
    if landstrom:
        primaer = Source.LANDSTROM
    elif v2l:
        primaer = Source.V2L
    else:
        primaer = Source.KEINE

    if primaer is not Source.KEINE:
        komfort = primaer
    elif bluetti_ok:
        komfort = Source.BLUETTI
    else:
        komfort = Source.KEINE
    return SourceState(primaer=primaer, komfort=komfort)


def bluetti_available(soc: float | None, min_soc: float) -> bool:
    """Bluetti darf liefern, solange der Ladestand über der Reserve liegt.

    Unbekannter Ladestand gilt als verfügbar (die Bluetti schützt sich selbst).
    """
    if soc is None:
        return True
    return soc > min_soc


def compute_balance(sources: SourceState, loads: list[Load], limits: Limits) -> Balance:
    """Leistung je Bus, Reserve und Überlast der speisenden Quelle berechnen."""
    p_primaer = sum(l.power_w for l in loads if l.is_on and l.bus is Bus.PRIMAER)
    p_komfort = sum(l.power_w for l in loads if l.is_on and l.bus is Bus.KOMFORT)

    unpowered: list[str] = []
    if sources.primaer is not Source.KEINE:
        # Beide Busse hängen an derselben Quelle.
        limit = limits.for_source(sources.primaer)
        load = p_primaer + p_komfort
    elif sources.komfort is Source.BLUETTI:
        limit = limits.for_source(Source.BLUETTI)
        load = p_komfort
        unpowered = [l.load_id for l in loads if l.is_on and l.bus is Bus.PRIMAER]
    else:
        limit = 0.0
        load = 0.0
        unpowered = [l.load_id for l in loads if l.is_on]

    headroom = limit - load
    return Balance(
        sources=sources,
        power_primaer_w=p_primaer,
        power_komfort_w=p_komfort,
        limit_w=limit,
        load_w=load,
        headroom_w=headroom,
        overload=limit > 0 and load > limit,
        unpowered_loads=unpowered,
    )


def select_loads_to_shed(sources: SourceState, loads: list[Load], limits: Limits) -> list[str]:
    """Verbraucher bestimmen, die abgeschaltet werden, bis die Grenze eingehalten ist.

    Reihenfolge: höchste Prioritätszahl zuerst, bei Gleichstand der größte Verbraucher.
    Es werden nur eingeschaltete, abwerfbare Verbraucher der speisenden Quelle betrachtet.
    """
    balance = compute_balance(sources, loads, limits)
    if not balance.overload:
        return []

    if sources.primaer is not Source.KEINE:
        candidates = [l for l in loads if l.is_on and l.sheddable]
    else:
        candidates = [l for l in loads if l.is_on and l.sheddable and l.bus is Bus.KOMFORT]
    candidates.sort(key=lambda l: (-l.priority, -l.power_w, l.load_id))

    excess = balance.load_w - balance.limit_w
    shed: list[str] = []
    for load in candidates:
        if excess <= 0:
            break
        if load.power_w <= 0:
            continue
        shed.append(load.load_id)
        excess -= load.power_w
    return shed


def interlock_partners(
    turned_on: str, pairs: list[tuple[str, str]], is_on: dict[str, bool]
) -> list[str]:
    """Partner, die ausgeschaltet werden, weil `turned_on` gerade eingeschaltet wurde.

    Regel: Der zuletzt eingeschaltete Verbraucher gewinnt.
    """
    result: list[str] = []
    for a, b in pairs:
        partner = b if a == turned_on else a if b == turned_on else None
        if partner and is_on.get(partner, False) and partner not in result:
            result.append(partner)
    return result
