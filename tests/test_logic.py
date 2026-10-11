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


def _flex(load_id, bus, nominal, on=False, power=0.0):
    return Load(load_id, bus, on, power if on else 0.0, nominal_w=nominal, flexible=True)


def test_freigabe_boiler_und_laden_bei_reserve():
    s = logic.resolve_sources(False, True, True)  # V2L 3500 W
    loads = [
        _load("kuehlschrank", Bus.KOMFORT, 60),
        _flex("boiler", Bus.PRIMAER, 1000),
        _flex("laden", Bus.PRIMAER, 2200),
    ]
    r = logic.compute_releases(s, loads, LIMITS, margin_w=200)
    # 60 + 1000 + 200 <= 3500 -> Boiler frei; 1060 + 2200 + 200 = 3460 <= 3500 -> Laden frei
    assert r == {"boiler": True, "laden": True}


def test_freigabe_induktion_hat_vorrang():
    s = logic.resolve_sources(False, True, True)
    loads = [
        _load("induktion", Bus.PRIMAER, 2800),
        _flex("boiler", Bus.PRIMAER, 1000, on=True, power=1000),
        _flex("laden", Bus.PRIMAER, 2200),
    ]
    r = logic.compute_releases(s, loads, LIMITS, margin_w=200)
    assert r == {"boiler": False, "laden": False}


def test_freigabe_reihenfolge_ist_prioritaet():
    s = logic.resolve_sources(True, False, True)  # Landstrom 2300 W
    loads = [_flex("boiler", Bus.PRIMAER, 1000), _flex("laden", Bus.PRIMAER, 2200)]
    r = logic.compute_releases(s, loads, LIMITS, margin_w=200)
    assert r == {"boiler": True, "laden": False}


def test_freigabe_laufender_verbraucher_zaehlt_gemessen():
    s = logic.resolve_sources(True, False, True)
    loads = [_flex("laden", Bus.PRIMAER, 2200, on=True, power=1500)]
    assert logic.compute_releases(s, loads, LIMITS, margin_w=200) == {"laden": True}


def test_keine_freigabe_ohne_quelle_des_busses():
    s = logic.resolve_sources(False, False, True)  # nur Solargenerator -> Primärbus spannungslos
    loads = [_flex("boiler", Bus.PRIMAER, 1000), _flex("steckdose", Bus.KOMFORT, 500)]
    r = logic.compute_releases(s, loads, LIMITS, margin_w=200)
    assert r == {"boiler": False, "steckdose": True}
