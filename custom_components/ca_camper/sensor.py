"""Sensoren: aktive Quellen, Busleistungen, Grenze und Reserve."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CamperConfigEntry
from .controller import CamperController
from .entity import CamperEntity
from .logic import Source

SOURCE_OPTIONS = [s.value for s in Source]


@dataclass(frozen=True, kw_only=True)
class CamperSensorDescription(SensorEntityDescription):
    """Beschreibung mit Wertfunktion."""

    value_fn: Callable[[CamperController], str | float | None]


def _bal(fn: Callable) -> Callable[[CamperController], float | str | None]:
    return lambda c: fn(c.balance) if c.balance else None


SENSORS: tuple[CamperSensorDescription, ...] = (
    CamperSensorDescription(
        key="quelle_primaerbus",
        device_class=SensorDeviceClass.ENUM,
        options=SOURCE_OPTIONS,
        value_fn=_bal(lambda b: b.sources.primaer.value),
    ),
    CamperSensorDescription(
        key="quelle_komfortbus",
        device_class=SensorDeviceClass.ENUM,
        options=SOURCE_OPTIONS,
        value_fn=_bal(lambda b: b.sources.komfort.value),
    ),
    CamperSensorDescription(
        key="leistung_primaerbus",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_bal(lambda b: round(b.power_primaer_w, 1)),
    ),
    CamperSensorDescription(
        key="leistung_komfortbus",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_bal(lambda b: round(b.power_komfort_w, 1)),
    ),
    CamperSensorDescription(
        key="leistungsgrenze",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_bal(lambda b: round(b.limit_w, 1)),
    ),
    CamperSensorDescription(
        key="leistungsreserve",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        value_fn=_bal(lambda b: round(b.headroom_w, 1)),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CamperConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensoren anlegen."""
    controller = entry.runtime_data
    async_add_entities(CamperSensor(controller, d) for d in SENSORS)


class CamperSensor(CamperEntity, SensorEntity):
    """Sensor auf Basis der Controller-Bilanz."""

    entity_description: CamperSensorDescription

    def __init__(self, controller: CamperController, description: CamperSensorDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | float | None:
        """Aktueller Wert."""
        return self.entity_description.value_fn(self.controller)
