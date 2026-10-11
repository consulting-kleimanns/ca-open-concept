"""Reine Entscheidungslogik des CA-Camper-Energiemanagers (ohne Home-Assistant-Abhängigkeit).

Bildet den Open-Concept-Elektroplan ab:
- VS1: Landstrom vor Fahrzeug-V2L  -> Primärbus
- VS2: Solargenerator vor Primärbus -> Komfortbus

Normalfall: zwei unabhängige Kreise – Primärbus an Landstrom/V2L, Komfortbus am Solargenerator.
Nur wenn der Solargenerator unter seiner Reserve liegt, speist der Primärbus auch den Komfortbus;
dann teilen sich beide Busse die Grenze dieser Quelle. Ohne Landstrom/V2L ist der Primärbus spannungslos.

Verbraucher mit fester Nutzung (Induktion, DauerShower, Kühlschrank …) werden nie geschaltet.
Verbraucher „nur mit Reserve“ (Boiler-Heizstab, Laden des Solargenerators) erhalten eine
Freigabe, solange die Grenze der speisenden Quelle sie zusätzlich trägt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Source(StrEnum):
    """Mögliche Einspeisungen."""

    LANDSTROM = "landstrom"
    V2L = "v2l"
    SOLARGENERATOR = "solargenerator"
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
    generator_w: float

    def for_source(self, source: Source) -> float:
        """Grenze der Quelle; ohne Quelle 0 W."""
        return {
            Source.LANDSTROM: self.landstrom_w,
            Source.V2L: self.v2l_w,
            Source.SOLARGENERATOR: self.generator_w,
        }.get(source, 0.0)


@dataclass(frozen=True)
class Load:
    """Ein geschalteter Verbraucher (ein Shelly-Kanal)."""

    load_id: str
    bus: Bus
    is_on: bool
    power_w: float  # gemessene oder nominale Leistung, wenn eingeschaltet
    nominal_w: float = 0.0  # Nennleistung – Bedarf, wenn (noch) nichts gemessen wird
    flexible: bool = False  # „nur mit Reserve“: läuft nur, solange die Quelle ihn trägt

    @property
    def demand_w(self) -> float:
        """Leistung, die der Verbraucher beim Laufen beansprucht."""
        if self.is_on and self.power_w > 0:
            return self.power_w
        return self.nominal_w


@dataclass(frozen=True)
class SourceState:
    """Ergebnis der Vorrangschaltungen."""

    primaer: Source
    komfort: Source


@dataclass
class Balance:
    """Leistungsbilanz je Bus. Teilen sich beide Busse eine Quelle, gilt deren Reserve für beide."""

    sources: SourceState
    power_primaer_w: float
    power_komfort_w: float
    limit_primaer_w: float
    headroom_primaer_w: float
    limit_komfort_w: float
    headroom_komfort_w: float
    overload: bool
    unpowered_loads: list[str] = field(default_factory=list)


def resolve_sources(landstrom: bool, v2l: bool, generator_ok: bool) -> SourceState:
    """Vorrangschaltungen VS1 und VS2 nachbilden."""
    if landstrom:
        primaer = Source.LANDSTROM
    elif v2l:
        primaer = Source.V2L
    else:
        primaer = Source.KEINE

    komfort = Source.SOLARGENERATOR if generator_ok else primaer
    return SourceState(primaer=primaer, komfort=komfort)


def generator_available(soc: float | None, min_soc: float) -> bool:
    """Der Solargenerator gilt als Quelle, solange der Ladestand über der Reserve liegt.

    Unbekannter Ladestand gilt als verfügbar (das Gerät schützt sich selbst).
    """
    if soc is None:
        return True
    return soc > min_soc


def compute_balance(sources: SourceState, loads: list[Load], limits: Limits) -> Balance:
    """Leistung, Grenze und Reserve je Bus berechnen."""
    p_primaer = sum(l.power_w for l in loads if l.is_on and l.bus is Bus.PRIMAER)
    p_komfort = sum(l.power_w for l in loads if l.is_on and l.bus is Bus.KOMFORT)

    usage: dict[Source, float] = {}
    for bus, power in ((Bus.PRIMAER, p_primaer), (Bus.KOMFORT, p_komfort)):
        src = _powered(sources, bus)
        if src is not Source.KEINE:
            usage[src] = usage.get(src, 0.0) + power

    def _limit(bus: Bus) -> float:
        return limits.for_source(_powered(sources, bus))

    def _headroom(bus: Bus) -> float:
        src = _powered(sources, bus)
        return 0.0 if src is Source.KEINE else limits.for_source(src) - usage[src]

    unpowered = [l.load_id for l in loads if l.is_on and _powered(sources, l.bus) is Source.KEINE]
    return Balance(
        sources=sources,
        power_primaer_w=p_primaer,
        power_komfort_w=p_komfort,
        limit_primaer_w=_limit(Bus.PRIMAER),
        headroom_primaer_w=_headroom(Bus.PRIMAER),
        limit_komfort_w=_limit(Bus.KOMFORT),
        headroom_komfort_w=_headroom(Bus.KOMFORT),
        overload=any(usage[src] > limits.for_source(src) for src in usage),
        unpowered_loads=unpowered,
    )


def _powered(sources: SourceState, bus: Bus) -> Source:
    """Quelle, die einen Bus gerade speist."""
    return sources.primaer if bus is Bus.PRIMAER else sources.komfort


def compute_releases(
    sources: SourceState,
    loads: list[Load],
    limits: Limits,
    margin_w: float,
    blocked: frozenset[str] = frozenset(),
    waiting: frozenset[str] = frozenset(),
) -> dict[str, bool]:
    """Freigabe je Verbraucher „nur mit Reserve“.

    Feste Verbraucher zählen mit ihrer aktuellen Leistung. Die Reserve-Verbraucher werden in der
    konfigurierten Reihenfolge (= Priorität) hinzugenommen, solange Last + Bedarf + Sicherheitsabstand
    die Grenze der gemeinsamen Quelle nicht übersteigen. Ein laufender Verbraucher zählt mit seiner
    Messung, ein ausgeschalteter mit seiner Nennleistung. Verbraucher in ``blocked`` erhalten keine
    Freigabe (z. B. Laden des Solargenerators aus V2L, solange dessen Ladestand hoch genug ist).
    Reserve belegen nur Verbraucher, die laufen oder pausiert auf Freigabe warten (``waiting``);
    ein ausgeschalteter, nicht wartender Verbraucher blockiert niemanden.
    """
    releases: dict[str, bool] = {}
    groups: dict[Source, float] = {}
    for load in loads:
        src = _powered(sources, load.bus)
        if src is Source.KEINE:
            continue
        if not load.flexible and load.is_on:
            groups[src] = groups.get(src, 0.0) + load.power_w

    for load in loads:
        if not load.flexible:
            continue
        src = _powered(sources, load.bus)
        if src is Source.KEINE or load.load_id in blocked:
            releases[load.load_id] = False
            continue
        used = groups.get(src, 0.0)
        ok = used + load.demand_w + margin_w <= limits.for_source(src)
        releases[load.load_id] = ok
        if ok and (load.is_on or load.load_id in waiting):
            groups[src] = used + load.demand_w
    return releases


def v2l_charge_needed(soc: float | None, start_soc: float, stop_soc: float, previous: bool) -> bool:
    """Laden des Solargenerators aus der Fahrzeugbatterie nur bei niedrigem Ladestand (Hysterese).

    Unter ``start_soc`` beginnt das Laden, ab ``stop_soc`` endet es, dazwischen bleibt der letzte
    Zustand. Unbekannter Ladestand: kein Laden aus dem Fahrzeug.
    """
    if soc is None:
        return False
    if soc < start_soc:
        return True
    if soc >= stop_soc:
        return False
    return previous
