"""Konstanten für den CA-Camper-Energiemanager."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ca_camper"

# Quellen (entry.data, änderbar über die Optionen)
CONF_LANDSTROM: Final = "landstrom_entity"
CONF_V2L: Final = "v2l_entity"
CONF_GENERATOR_SOC: Final = "generator_soc_entity"
CONF_GENERATOR_MIN_SOC: Final = "generator_min_soc"
CONF_LIMIT_LANDSTROM: Final = "limit_landstrom_w"
CONF_LIMIT_V2L: Final = "limit_v2l_w"
CONF_LIMIT_GENERATOR: Final = "limit_generator_w"
CONF_MARGIN: Final = "release_margin_w"
CONF_DELAY_OFF: Final = "release_delay_off_s"
CONF_DELAY_ON: Final = "release_delay_on_s"

# Verbraucher (entry.options)
CONF_LOADS: Final = "loads"

# Felder eines Verbrauchers
LOAD_NAME: Final = "name"
LOAD_SWITCH: Final = "switch_entity"
LOAD_POWER: Final = "power_entity"
LOAD_BUS: Final = "bus"
LOAD_NOMINAL: Final = "nominal_w"
LOAD_FLEXIBLE: Final = "flexible"  # „nur mit Reserve“

# Vorgaben – Werte des eigenen Fahrzeugs und Geräts prüfen und anpassen
DEFAULT_LIMIT_LANDSTROM: Final = 2300  # 10-A-Absicherung am Stellplatz
DEFAULT_LIMIT_V2L: Final = 3500
DEFAULT_LIMIT_GENERATOR: Final = 3600  # z. B. FOSSiBOT F3600 Pro, AC-Dauerleistung
DEFAULT_GENERATOR_MIN_SOC: Final = 10
DEFAULT_MARGIN: Final = 200  # Sicherheitsabstand zur Grenze
DEFAULT_DELAY_OFF: Final = 2  # s bis zur Pause eines Reserve-Verbrauchers
DEFAULT_DELAY_ON: Final = 30  # s stabile Reserve, bevor er wieder anläuft

ON_STATES: Final = frozenset({"on", "true", "home", "connected", "open"})
