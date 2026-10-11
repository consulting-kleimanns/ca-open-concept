"""Tests der reinen Bilanzlogik."""

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).parents[1] / "custom_components" / "ca_camper" / "logic.py"
_spec = importlib.util.spec_from_file_location("ca_camper_logic", _PATH)
logic = importlib.util.module_from_spec(_spec)
sys.modules["ca_camper_logic"] = logic
_spec.loader.exec_module(logic)

Bus, Load, Limits, Source = logic.Bus, logic.Load, logic.Limits, logic.Source
LIMITS = Limits(landstrom_w=2300, v2l_w=3500, generator_w=3600)


def _load(load_id, bus, power, on=True):
    return Load(load_id, bus, on, power)


def test_vs1_landstrom_hat_vorrang():
    s = logic.resolve_sources(landstrom=True, v2l=True, generator_ok=True)
    assert s.primaer is Source.LANDSTROM and s.komfort is Source.LANDSTROM


def test_vs1_v2l_wenn_kein_landstrom():
    s = logic.resolve_sources(landstrom=False, v2l=True, generator_ok=True)
    assert s.primaer is Source.V2L and s.komfort is Source.V2L


def test_vs2_solargenerator_nur_ohne_primaerbus():
    s = logic.resolve_sources(landstrom=False, v2l=False, generator_ok=True)
    assert s.primaer is Source.KEINE and s.komfort is Source.SOLARGENERATOR


def test_keine_quelle():
    s = logic.resolve_sources(False, False, False)
    assert s.primaer is Source.KEINE and s.komfort is Source.KEINE


def test_generator_reserve():
    assert logic.generator_available(50, 10)
    assert not logic.generator_available(10, 10)
    assert logic.generator_available(None, 10)


def test_bilanz_gemeinsame_quelle():
    s = logic.resolve_sources(False, True, True)
    loads = [
        _load("induktion", Bus.PRIMAER, 3000),
        _load("kuehlschrank", Bus.KOMFORT, 60),
        _load("aus", Bus.KOMFORT, 999, on=False),
    ]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.load_w == 3060 and b.limit_w == 3500
    assert b.headroom_w == 440 and not b.overload


def test_bilanz_solargenerator_primaer_spannungslos():
    s = logic.resolve_sources(False, False, True)
    loads = [_load("induktion", Bus.PRIMAER, 3000), _load("dusche", Bus.KOMFORT, 2400)]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.load_w == 2400 and b.limit_w == 3600 and not b.overload
    assert b.unpowered_loads == ["induktion"]


def test_ueberlast_wird_nur_gemeldet():
    s = logic.resolve_sources(True, False, True)  # 2300 W Landstrom
    b = logic.compute_balance(s, [_load("induktion", Bus.PRIMAER, 3000)], LIMITS)
    assert b.overload and b.headroom_w == -700
