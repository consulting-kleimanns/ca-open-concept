"""Messwerte: Leistung je Kreis, Hausbatterien, Raumklima, Wasser, Fahrzeug."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SimConfigEntry
from .entity import SimEntity
from .model import CIRCUITS, CamperModel, Ladezustand
from .switch import KREISE

W, C, P = UnitOfPower.WATT, UnitOfTemperature.CELSIUS, PERCENTAGE
POWER, TEMP, BAT, HUM, ENUM = (
    SensorDeviceClass.POWER,
    SensorDeviceClass.TEMPERATURE,
    SensorDeviceClass.BATTERY,
    SensorDeviceClass.HUMIDITY,
    SensorDeviceClass.ENUM,
)


@dataclass(frozen=True)
class Messwert:
    key: str
    name: str
    value: Callable[[CamperModel], Any]
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    icon: str | None = None
    options: list[str] | None = None
    precision: int | None = None


def _power(key: str) -> Callable[[CamperModel], float]:
    return lambda m: round(m.last.power[key])


MESSWERTE = (
    *(Messwert(f"{k}_leistung", f"{KREISE[k][0]} Leistung", _power(k), W, POWER) for k in CIRCUITS),
    Messwert(
        "induktion_leistung",
        "Kochfeld Leistung",
        lambda m: m.last.induktion_w,
        W,
        POWER,
        "mdi:stove",
    ),
    Messwert(
        "dusche_leistung", "Dusche Leistung", lambda m: m.last.dusche_w, W, POWER, "mdi:shower"
    ),
    Messwert(
        "heizung_leistung",
        "Heizung Leistung",
        lambda m: round(m.last.heizung_w),
        W,
        POWER,
        "mdi:radiator",
    ),
    Messwert(
        "infrarot_leistung",
        "Infrarotheizung Leistung",
        lambda m: m.last.infrarot_w,
        W,
        POWER,
        "mdi:heat-wave",
    ),
    Messwert(
        "bordstrom_leistung",
        "Bordstrom Leistung",
        lambda m: round(m.last.komfort_w),
        W,
        POWER,
        "mdi:home-lightning-bolt",
    ),
    Messwert(
        "aussenstrom_leistung",
        "Strom von außen Leistung",
        lambda m: round(m.last.primaer_w),
        W,
        POWER,
        "mdi:transmission-tower",
    ),
    Messwert(
        "hausbatterie_1_ladestand",
        "Hausbatterie 1",
        lambda m: round(m.s.eco[0], 1),
        P,
        BAT,
        precision=0,
    ),
    Messwert(
        "hausbatterie_2_ladestand",
        "Hausbatterie 2",
        lambda m: round(m.s.eco[1], 1),
        P,
        BAT,
        precision=0,
    ),
    Messwert(
        "hausbatterie_ladestand",
        "Hausbatterien",
        lambda m: round(m.eco_avg, 1),
        P,
        BAT,
        precision=0,
    ),
    Messwert("innen_temperatur", "Innentemperatur", lambda m: round(m.s.innen, 1), C, TEMP),
    Messwert("innen_feuchte", "Luftfeuchte innen", lambda m: round(m.s.feuchte), P, HUM),
    Messwert(
        "taupunkt", "Taupunkt", lambda m: round(m.taupunkt, 1), C, TEMP, "mdi:water-thermometer"
    ),
    Messwert(
        "wasser_temperatur",
        "Wassertemperatur Boiler",
        lambda m: round(m.s.wasser),
        C,
        TEMP,
        "mdi:water-boiler",
    ),
    Messwert("aussentemperatur", "Außentemperatur", lambda m: m.p.aussen_c, C, TEMP),
    Messwert("fahrbatterie", "Fahrbatterie", lambda m: round(m.s.car), P, BAT),
    Messwert(
        "reichweite",
        "Reichweite",
        lambda m: round(m.reichweite_km),
        UnitOfLength.KILOMETERS,
        SensorDeviceClass.DISTANCE,
        "mdi:map-marker-distance",
    ),
    Messwert(
        "fahrzeug_energie",
        "Energie der Fahrbatterie",
        lambda m: round(m.s.car / 100 * m.p.car_wh / 1000, 1),
        UnitOfEnergy.KILO_WATT_HOUR,
        SensorDeviceClass.ENERGY_STORAGE,
    ),
    Messwert(
        "kilometerstand",
        "Kilometerstand",
        lambda m: round(m.s.km),
        UnitOfLength.KILOMETERS,
        SensorDeviceClass.DISTANCE,
        "mdi:counter",
    ),
    Messwert(
        "ladeleistung",
        "Ladeleistung",
        lambda m: m.p.wallbox_w / 1000 if m.s.car_charging else 0,
        UnitOfPower.KILO_WATT,
        POWER,
        "mdi:flash",
    ),
    Messwert(
        "restladezeit",
        "Restladezeit",
        lambda m: round(m.restladezeit_min),
        UnitOfTime.MINUTES,
        SensorDeviceClass.DURATION,
        "mdi:timer-outline",
    ),
    Messwert(
        "ladezustand",
        "Ladezustand",
        lambda m: m.ladezustand.value,
        device_class=ENUM,
        icon="mdi:ev-station",
        options=[z.value for z in Ladezustand],
    ),
    Messwert(
        "stecker",
        "Stecker",
        lambda m: "plugged" if m.stecker else "unplugged",
        device_class=ENUM,
        icon="mdi:power-plug",
        options=["plugged", "unplugged"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SimConfigEntry, add: AddEntitiesCallback
) -> None:
    hub = entry.runtime_data
    add([SimSensor(hub, d) for d in MESSWERTE])


class SimSensor(SimEntity, SensorEntity):
    """Ein Messwert der Simulation."""

    def __init__(self, hub, d: Messwert) -> None:
        super().__init__(hub, "sensor", d.key, d.name, d.icon)
        self._d = d
        self._attr_native_unit_of_measurement = d.unit
        self._attr_device_class = d.device_class
        if d.options:
            self._attr_options = d.options
        elif d.device_class is not ENUM:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if d.precision is not None:
            self._attr_suggested_display_precision = d.precision

    @property
    def native_value(self) -> Any:
        return self._d.value(self.m)
