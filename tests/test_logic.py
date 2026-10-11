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
LIMITS = Limits(landstrom_w=2300, v2l_w=3700, generator_w=3600)


def _load(load_id, bus, power, on=True):
    return Load(load_id, bus, on, power)


def test_vs1_landstrom_hat_vorrang():
    s = logic.resolve_sources(landstrom=True, v2l=True, generator_ok=True)
    assert s.primaer is Source.LANDSTROM and s.komfort is Source.SOLARGENERATOR


def test_vs1_v2l_wenn_kein_landstrom():
    s = logic.resolve_sources(landstrom=False, v2l=True, generator_ok=True)
    assert s.primaer is Source.V2L and s.komfort is Source.SOLARGENERATOR


def test_vs2_solargenerator_speist_komfortbus():
    s = logic.resolve_sources(landstrom=False, v2l=False, generator_ok=True)
    assert s.primaer is Source.KEINE and s.komfort is Source.SOLARGENERATOR


def test_vs2_primaerbus_nur_wenn_generator_unter_reserve():
    s = logic.resolve_sources(landstrom=False, v2l=True, generator_ok=False)
    assert s.primaer is Source.V2L and s.komfort is Source.V2L


def test_keine_quelle():
    s = logic.resolve_sources(False, False, False)
    assert s.primaer is Source.KEINE and s.komfort is Source.KEINE


def test_generator_reserve():
    assert logic.generator_available(50, 10)
    assert not logic.generator_available(10, 10)
    assert logic.generator_available(None, 10)


def test_bilanz_zwei_unabhaengige_kreise():
    s = logic.resolve_sources(False, True, True)  # V2L + Solargenerator
    loads = [
        _load("induktion", Bus.PRIMAER, 3000),
        _load("dusche", Bus.KOMFORT, 2400),
        _load("kuehlschrank", Bus.KOMFORT, 60),
        _load("aus", Bus.KOMFORT, 999, on=False),
    ]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.limit_primaer_w == 3700 and b.headroom_primaer_w == 700
    assert b.limit_komfort_w == 3600 and b.headroom_komfort_w == 1140
    assert not b.overload


def test_bilanz_gemeinsame_quelle_wenn_generator_leer():
    s = logic.resolve_sources(False, True, False)
    loads = [_load("induktion", Bus.PRIMAER, 3000), _load("kuehlschrank", Bus.KOMFORT, 60)]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.headroom_primaer_w == b.headroom_komfort_w == 640


def test_bilanz_solargenerator_primaer_spannungslos():
    s = logic.resolve_sources(False, False, True)
    loads = [_load("induktion", Bus.PRIMAER, 3000), _load("dusche", Bus.KOMFORT, 2400)]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.limit_komfort_w == 3600 and b.headroom_komfort_w == 1200 and not b.overload
    assert b.unpowered_loads == ["induktion"]


def test_ueberlast_wird_nur_gemeldet():
    s = logic.resolve_sources(True, False, True)  # 2300 W Landstrom
    b = logic.compute_balance(s, [_load("induktion", Bus.PRIMAER, 3000)], LIMITS)
    assert b.overload and b.headroom_primaer_w == -700


def _flex(load_id, bus, nominal, on=False, power=0.0):
    return Load(load_id, bus, on, power if on else 0.0, nominal_w=nominal, flexible=True)


def test_freigabe_boiler_und_laden_bei_reserve():
    s = logic.resolve_sources(False, True, True)  # V2L 3700 W, Komfortbus am Solargenerator
    loads = [
        _load("dusche", Bus.KOMFORT, 2400),
        _flex("boiler", Bus.PRIMAER, 1000),
        _flex("laden", Bus.PRIMAER, 2200),
    ]
    r = logic.compute_releases(s, loads, LIMITS, margin_w=200)
    # Dusche läuft am Solargenerator; Primärbus: 1000 + 200 und 1000 + 2200 + 200 <= 3700
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


def test_laden_aus_fahrzeug_gesperrt():
    s = logic.resolve_sources(False, True, True)
    loads = [_flex("laden", Bus.PRIMAER, 2200)]
    r = logic.compute_releases(s, loads, LIMITS, 200, blocked=frozenset({"laden"}))
    assert r == {"laden": False}


def test_laden_aus_fahrzeug_hysterese():
    need = logic.v2l_charge_needed
    assert need(29, 30, 80, previous=False)
    assert need(50, 30, 80, previous=True)  # lädt weiter bis 80 %
    assert not need(50, 30, 80, previous=False)  # startet nicht über 30 %
    assert not need(80, 30, 80, previous=True)
    assert not need(None, 30, 80, previous=True)


def test_ausgeschalteter_reserve_verbraucher_blockiert_nicht():
    s = logic.resolve_sources(True, False, True)  # Landstrom 2300 W
    loads = [
        _flex("boiler", Bus.PRIMAER, 1000),
        _flex("laden", Bus.PRIMAER, 1500, on=True, power=1500),
    ]
    r = logic.compute_releases(s, loads, LIMITS, 200)
    assert r["laden"] is True
    # wartet der Boiler (pausiert), hat er Vorrang
    r = logic.compute_releases(s, loads, LIMITS, 200, waiting=frozenset({"boiler"}))
    assert r == {"boiler": True, "laden": False}
