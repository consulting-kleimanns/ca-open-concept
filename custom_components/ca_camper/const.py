"""Konstanten für den CA-Camper-Energiemanager."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ca_camper"

# Quellen (entry.data)
CONF_LANDSTROM: Final = "landstrom_entity"
CONF_V2L: Final = "v2l_entity"
CONF_BLUETTI_SOC: Final = "bluetti_soc_entity"
CONF_BLUETTI_MIN_SOC: Final = "bluetti_min_soc"
CONF_LIMIT_LANDSTROM: Final = "limit_landstrom_w"
CONF_LIMIT_V2L: Final = "limit_v2l_w"
CONF_LIMIT_BLUETTI: Final = "limit_bluetti_w"
CONF_SHED_DELAY: Final = "shed_delay_s"

# Verbraucher und Verriegelungen (entry.options)
CONF_LOADS: Final = "loads"
CONF_INTERLOCKS: Final = "interlocks"

# Felder eines Verbrauchers
LOAD_ID: Final = "id"
LOAD_NAME: Final = "name"
LOAD_SWITCH: Final = "switch_entity"
LOAD_POWER: Final = "power_entity"
LOAD_BUS: Final = "bus"
LOAD_PRIORITY: Final = "priority"
LOAD_NOMINAL: Final = "nominal_w"
LOAD_SHEDDABLE: Final = "sheddable"

# Felder einer Verriegelung
LOCK_A: Final = "entity_a"
LOCK_B: Final = "entity_b"

# Vorgaben – Werte des eigenen Fahrzeugs prüfen und anpassen
DEFAULT_LIMIT_LANDSTROM: Final = 2300  # 10-A-Absicherung am Stellplatz
DEFAULT_LIMIT_V2L: Final = 3500
DEFAULT_LIMIT_BLUETTI: Final = 2200
DEFAULT_BLUETTI_MIN_SOC: Final = 20
DEFAULT_SHED_DELAY: Final = 3

EVENT_LOAD_SHED: Final = f"{DOMAIN}_load_shed"
EVENT_INTERLOCK: Final = f"{DOMAIN}_interlock"

ON_STATES: Final = frozenset({"on", "true", "home", "connected", "open"})
