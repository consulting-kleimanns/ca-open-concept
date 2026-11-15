"""Physikmodell der Camper-Simulation (ohne Home-Assistant-Abhängigkeit).

Bildet die „Hardware“ eines CA-Campers nach, damit die echte Integration ``ca_camper`` darauf
laufen kann: Stromquellen (Landstrom, V2L), zwei Hausbatterien, 230-V-Kreise mit Leistung,
Heizung, Boiler, Licht, Fahrzeugbatterie. Alle Werte sind Musterwerte und über ``Params``
anpassbar.

Ablauf: Home Assistant ruft regelmäßig ``tick(dt_min)`` auf. Schaltvorgänge (auch die
Freigaben von ``ca_camper``) ändern ``State`` direkt; ``tick`` rechnet Leistungen, Ladestände
und Temperaturen fort.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Standort(StrEnum):
    """Stromsituation am Standort („Wo steht der Camper?“)."""

    CAMPINGPLATZ_16A = "campingplatz_16a"
    CAMPINGPLATZ_10A = "campingplatz_10a"
    FREI_V2L = "frei_v2l"
    ZUHAUSE_WALLBOX = "zuhause_wallbox"


class Boiler(StrEnum):
    """Betriebsart des Boilers."""

    AUS = "Aus"
    ECO = "Eco"
    HIGH = "High"
    BOOST = "Boost"


class Ladezustand(StrEnum):
    """Ladezustand des Fahrzeugs (Werte wie in der Renault-Integration)."""

    NOT_IN_CHARGE = "not_in_charge"
    CHARGE_IN_PROGRESS = "charge_in_progress"
    CHARGE_ENDED = "charge_ended"
    V2L_CONNECTED = "v2l_connected"


@dataclass
class Params:
    """Musterwerte – an das konkrete Fahrzeug anpassen."""

    eco_wh: float = 2016.0  # je Hausbatterie
    eco_charge_w: float = 1000.0  # Ladeleistung je Hausbatterie
    eco_reserve: float = 20.0  # % – darunter versorgt der Primärbus den Komfortbus
    v2l_w: float = 3700.0
    landstrom_10a_w: float = 2300.0
    landstrom_16a_w: float = 3600.0
    car_wh: float = 87000.0
    km_per_pct: float = 3.6
    wallbox_w: float = 11000.0
    induktion_w: float = 3000.0
    dusche_w: float = 2400.0
    boiler_w: float = 1000.0
    boiler_l: float = 10.0
    kuehlschrank_w: float = 70.0
    basis_w: float = 25.0  # Router, Pi, Displays
    heizung_eco_w: float = 900.0
    heizung_high_w: float = 1800.0
    infrarot_w: float = 400.0
    led_w: float = 15.0  # je Lichtleiste bei 100 %
    tv_w: float = 60.0
    laptop_w: float = 65.0  # Gerät an der Steckdose Heck
    aussen_c: float = 6.0
    kuechenlicht_nachlauf_min: float = 5.0


CIRCUITS = (
    "ac_01_induktion",
    "ac_05_dusche",
    "ac_06_kuehlschrank",
    "ac_03_generator_1",
    "ac_03_generator_2",
    "ac_04_reserve_1",
    "ac_04_reserve_2",
    "ac_02_boiler_heizstab",
    "ac_07_steckdose_heck",
    "ac_08_steckdose_trennwand",
    "reserve_3",
    "reserve_4",
)
LIGHTS = ("heck_links", "heck_rechts", "dusche", "kueche")


@dataclass
class Climate:
    """Heizkreis mit Zieltemperatur."""

    on: bool = False
    target: float = 21.0
    preset: str = "eco"


@dataclass
class State:
    """Veränderlicher Zustand der Simulation."""

    standort: Standort = Standort.FREI_V2L
    ort: str = ""
    circuits: dict[str, bool] = field(
        default_factory=lambda: {
            c: c.startswith(("ac_01", "ac_02", "ac_03", "ac_05", "ac_06")) for c in CIRCUITS
        }
    )
    lights: dict[str, int] = field(default_factory=lambda: dict.fromkeys(LIGHTS, 0))  # 0–255
    kuechenlicht_auto: bool = True
    bewegung_min: float = 0.0
    heizung: Climate = field(default_factory=Climate)
    wandthermostat: Climate = field(default_factory=lambda: Climate(target=22.0))
    boiler: Boiler = Boiler.ECO
    eco: list[float] = field(default_factory=lambda: [64.0, 70.0])
    car: float = 76.0
    km: float = 8250.0
    soll_ladestand: float = 90.0
    mindest_ladestand: float = 20.0
    car_charging: bool = False
    klima_fahrerhaus_min: float = 0.0
    hupe_min: float = 0.0
    lichthupe_min: float = 0.0
    innen: float = 13.5
    feuchte: float = 62.0
    wasser: float = 31.0
    kochen_min: float = 0.0
    duschen_min: float = 0.0
    media_on: bool = False


@dataclass
class Snapshot:
    """Ergebnis eines Rechenschritts (Anzeige- und Messwerte)."""

    landstrom: bool
    v2l: bool
    limit_w: float
    power: dict[str, float]  # Leistung je 230-V-Kreis
    induktion_w: float
    dusche_w: float
    heizung_w: float
    infrarot_w: float
    licht_w: float
    komfort_w: float
    eco_ok: bool
    primaer_w: float
    boiler_heizt: bool
    charge_w: tuple[float, float]


class CamperModel:
    """Rechnet den Zustand fort."""

    def __init__(self, params: Params | None = None, state: State | None = None) -> None:
        self.p = params or Params()
        self.s = state or State()
        self.last = self.snapshot()

    # --- Quellen --------------------------------------------------------------------------------

    @property
    def landstrom(self) -> bool:
        return self.s.standort in (
            Standort.CAMPINGPLATZ_10A,
            Standort.CAMPINGPLATZ_16A,
            Standort.ZUHAUSE_WALLBOX,
        )

    @property
    def stecker(self) -> bool:
        """Ladekabel am Fahrzeug (V2L-Adapter oder Wallbox)."""
        return self.s.standort in (Standort.FREI_V2L, Standort.ZUHAUSE_WALLBOX)

    @property
    def v2l(self) -> bool:
        """V2L liefert, solange die Fahrzeugbatterie über dem Mindest-Ladestand liegt."""
        return self.s.standort is Standort.FREI_V2L and self.s.car > self.s.mindest_ladestand

    @property
    def limit_w(self) -> float:
        if self.s.standort is Standort.CAMPINGPLATZ_10A:
            return self.p.landstrom_10a_w
        if self.landstrom:
            return self.p.landstrom_16a_w
        return self.p.v2l_w if self.v2l else 0.0

    @property
    def eco_avg(self) -> float:
        return sum(self.s.eco) / len(self.s.eco)

    @property
    def ladezustand(self) -> Ladezustand:
        if self.s.car_charging:
            return Ladezustand.CHARGE_IN_PROGRESS
        if self.s.standort is Standort.FREI_V2L:
            return Ladezustand.V2L_CONNECTED
        if self.stecker:
            return Ladezustand.CHARGE_ENDED
        return Ladezustand.NOT_IN_CHARGE

    @property
    def kuechenlicht(self) -> bool:
        return self.s.kuechenlicht_auto and self.s.bewegung_min > 0

    def boiler_target(self) -> float:
        return {Boiler.AUS: 0.0, Boiler.ECO: 45.0, Boiler.HIGH: 60.0, Boiler.BOOST: 60.0}[
            self.s.boiler
        ]

    # --- Rechenschritt --------------------------------------------------------------------------

    def snapshot(self) -> Snapshot:
        p, s = self.p, self.s
        light_levels = dict(s.lights)
        light_levels["kueche"] = 255 if self.kuechenlicht else 0
        licht_w = sum(v / 255 * p.led_w for v in light_levels.values())

        heizung_w = 0.0
        if s.heizung.on:
            heizt = s.innen < s.heizung.target
            heizung_w = (
                (p.heizung_high_w if s.heizung.preset == "high" else p.heizung_eco_w)
                if heizt
                else 30.0
            )
        infrarot_w = (
            p.infrarot_w if s.wandthermostat.on and s.innen < s.wandthermostat.target else 0.0
        )
        # Feste Verbraucher laufen nur, wenn ihr 230-V-Kreis eingeschaltet ist
        dusche_w = p.dusche_w if s.duschen_min > 0 and s.circuits["ac_05_dusche"] else 0.0
        induktion_w = p.induktion_w if s.kochen_min > 0 and s.circuits["ac_01_induktion"] else 0.0
        kuehl_w = p.kuehlschrank_w if s.circuits["ac_06_kuehlschrank"] else 0.0

        power = dict.fromkeys(CIRCUITS, 0.0)
        power["ac_01_induktion"] = induktion_w
        power["ac_05_dusche"] = dusche_w
        power["ac_06_kuehlschrank"] = kuehl_w
        if s.circuits["ac_07_steckdose_heck"]:
            power["ac_07_steckdose_heck"] = p.laptop_w
        boiler_heizt = (
            s.circuits["ac_02_boiler_heizstab"]
            and s.boiler is not Boiler.AUS
            and s.wasser < self.boiler_target() - 0.5
            and self.limit_w > 0
        )
        if boiler_heizt:
            power["ac_02_boiler_heizstab"] = p.boiler_w
        charge = [0.0, 0.0]
        for i, c in enumerate(("ac_03_generator_1", "ac_03_generator_2")):
            if s.circuits[c] and s.eco[i] < 99.5 and self.limit_w > 0:
                charge[i] = p.eco_charge_w
                power[c] = p.eco_charge_w

        komfort_w = (
            kuehl_w
            + p.basis_w
            + licht_w
            + heizung_w
            + infrarot_w
            + dusche_w
            + (p.tv_w if s.media_on else 0.0)
            + power["ac_07_steckdose_heck"]
        )
        eco_ok = self.eco_avg > p.eco_reserve
        primaer_w = induktion_w + sum(
            power[c] for c in CIRCUITS if c.startswith(("ac_02", "ac_03"))
        )
        if not eco_ok:
            primaer_w += komfort_w
        return Snapshot(
            landstrom=self.landstrom,
            v2l=self.v2l,
            limit_w=self.limit_w,
            power=power,
            induktion_w=induktion_w,
            dusche_w=dusche_w,
            heizung_w=heizung_w,
            infrarot_w=infrarot_w,
            licht_w=licht_w,
            komfort_w=komfort_w,
            eco_ok=eco_ok,
            primaer_w=primaer_w,
            boiler_heizt=boiler_heizt,
            charge_w=(charge[0], charge[1]),
        )

    def tick(self, dt_min: float) -> Snapshot:
        """Zustand um ``dt_min`` Minuten fortschreiben."""
        p, s = self.p, self.s
        snap = self.snapshot()
        h = dt_min / 60.0
        draw = snap.komfort_w / 2 if snap.eco_ok else 0.0
        for i in range(2):
            delta = (snap.charge_w[i] * 0.9 - draw) * h / p.eco_wh * 100
            s.eco[i] = max(0.0, min(100.0, s.eco[i] + delta))
        if s.standort is Standort.FREI_V2L and snap.limit_w > 0:
            s.car = max(0.0, s.car - snap.primaer_w * h / p.car_wh * 100)
        if s.car_charging:
            s.car = min(s.soll_ladestand, s.car + p.wallbox_w * h / p.car_wh * 100)
            if s.car >= s.soll_ladestand or s.standort is not Standort.ZUHAUSE_WALLBOX:
                s.car_charging = False

        # Wasser: 10 l, 1 kW ≈ 1,43 K/min; Wärmeverlust; Duschen zieht Warmwasser
        heat_k = p.boiler_w * 60 / (p.boiler_l * 4186)
        s.wasser += (heat_k if snap.boiler_heizt else 0.0) * dt_min
        s.wasser -= 0.015 * dt_min * (s.wasser - 12) / 30
        if s.duschen_min > 0:
            s.wasser -= 0.8 * dt_min
        s.wasser = max(10.0, s.wasser)

        gain = (
            snap.heizung_w / 900 * 0.12
            + snap.infrarot_w / 400 * 0.05
            + (0.03 if s.duschen_min > 0 else 0.0)
            + (0.02 if s.kochen_min > 0 else 0.0)
        )
        s.innen += gain * dt_min - 0.012 * dt_min * (s.innen - p.aussen_c) / 8
        s.feuchte += (0.6 if s.duschen_min > 0 else 0.0) + (0.3 if s.kochen_min > 0 else 0.0)
        s.feuchte -= 0.15 if snap.heizung_w > 100 else 0.02
        s.feuchte = max(35.0, min(80.0, s.feuchte))

        if s.kochen_min > 0:
            s.bewegung_min = max(s.bewegung_min, 3.0)
        for name in (
            "kochen_min",
            "duschen_min",
            "bewegung_min",
            "klima_fahrerhaus_min",
            "hupe_min",
            "lichthupe_min",
        ):
            setattr(s, name, max(0.0, getattr(s, name) - dt_min))

        self.last = self.snapshot()
        return self.last

    # --- Aktionen (Buttons) ---------------------------------------------------------------------

    def einsteigen(self) -> None:
        self.s.bewegung_min = max(self.s.bewegung_min, 1.0)

    def kueche_betreten(self) -> None:
        self.s.bewegung_min = self.p.kuechenlicht_nachlauf_min

    def kochen(self, minuten: float = 12.0) -> None:
        self.s.kochen_min = 0.0 if self.s.kochen_min > 0 else minuten

    def duschen(self, minuten: float = 10.0) -> None:
        self.s.duschen_min = 0.0 if self.s.duschen_min > 0 else minuten

    def laden_starten(self) -> bool:
        """Laden ist nur an der Wallbox möglich (bei V2L ist der Stecker belegt)."""
        if self.s.standort is Standort.ZUHAUSE_WALLBOX and self.s.car < self.s.soll_ladestand:
            self.s.car_charging = True
        return self.s.car_charging

    def set_standort(self, standort: Standort) -> None:
        self.s.standort = standort
        if standort is not Standort.ZUHAUSE_WALLBOX:
            self.s.car_charging = False

    @property
    def taupunkt(self) -> float:
        """Taupunkt nach Magnus-Formel."""
        import math

        a, b = 17.62, 243.12
        g = math.log(max(self.s.feuchte, 1) / 100) + a * self.s.innen / (b + self.s.innen)
        return b * g / (a - g)

    @property
    def reichweite_km(self) -> float:
        return self.s.car * self.p.km_per_pct

    @property
    def restladezeit_min(self) -> float:
        if not self.s.car_charging:
            return 0.0
        return max(
            0.0, (self.s.soll_ladestand - self.s.car) / 100 * self.p.car_wh / self.p.wallbox_w * 60
        )
