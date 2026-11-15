"""Konstanten der CA-Camper-Simulation."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "ca_camper_sim"
TICK_SECONDS: Final = 5  # Echtzeit-Intervall der Berechnung
SAVE_EVERY_TICKS: Final = 12  # Zustand etwa jede Minute sichern
ZEITRAFFER: Final = {"1×": 1, "10×": 10, "60×": 60}
DEFAULT_ZEITRAFFER: Final = "1×"
