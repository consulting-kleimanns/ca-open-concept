"""Tests der reinen Entscheidungslogik."""

import importlib.util
import pathlib
import sys

_PATH = pathlib.Path(__file__).parents[1] / "custom_components" / "ca_camper" / "logic.py"
_spec = importlib.util.spec_from_file_location("ca_camper_logic", _PATH)
logic = importlib.util.module_from_spec(_spec)
sys.modules["ca_camper_logic"] = logic
_spec.loader.exec_module(logic)

Bus, Load, Limits, Source = logic.Bus, logic.Load, logic.Limits, logic.Source
LIMITS = Limits(landstrom_w=2300, v2l_w=3500, bluetti_w=2200)


def _load(load_id, bus, prio, power, on=True, sheddable=True):
    return Load(load_id, bus, prio, on, power, sheddable)


def test_vs1_landstrom_hat_vorrang():
    s = logic.resolve_sources(landstrom=True, v2l=True, bluetti_ok=True)
    assert s.primaer is Source.LANDSTROM and s.komfort is Source.LANDSTROM


def test_vs1_v2l_wenn_kein_landstrom():
    s = logic.resolve_sources(landstrom=False, v2l=True, bluetti_ok=True)
    assert s.primaer is Source.V2L and s.komfort is Source.V2L


def test_vs2_bluetti_nur_ohne_primaerbus():
    s = logic.resolve_sources(landstrom=False, v2l=False, bluetti_ok=True)
    assert s.primaer is Source.KEINE and s.komfort is Source.BLUETTI


def test_keine_quelle():
    s = logic.resolve_sources(False, False, False)
    assert s.primaer is Source.KEINE and s.komfort is Source.KEINE


def test_bluetti_reserve():
    assert logic.bluetti_available(50, 20)
    assert not logic.bluetti_available(20, 20)
    assert logic.bluetti_available(None, 20)


def test_bilanz_gemeinsame_quelle():
    s = logic.resolve_sources(False, True, True)
    loads = [
        _load("induktion", Bus.PRIMAER, 5, 3000),
        _load("kuehlschrank", Bus.KOMFORT, 1, 60),
        _load("aus", Bus.KOMFORT, 5, 999, on=False),
    ]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.load_w == 3060 and b.limit_w == 3500
    assert b.headroom_w == 440 and not b.overload


def test_bilanz_bluetti_primaer_spannungslos():
    s = logic.resolve_sources(False, False, True)
    loads = [_load("induktion", Bus.PRIMAER, 5, 3000), _load("dusche", Bus.KOMFORT, 4, 2400)]
    b = logic.compute_balance(s, loads, LIMITS)
    assert b.load_w == 2400 and b.limit_w == 2200 and b.overload
    assert b.unpowered_loads == ["induktion"]


def test_lastabwurf_niedrigste_prioritaet_zuerst():
    s = logic.resolve_sources(True, False, True)  # 2300 W Landstrom
    loads = [
        _load("induktion", Bus.PRIMAER, 6, 2000),
        _load("bluetti_laden", Bus.PRIMAER, 9, 500),
        _load("kuehlschrank", Bus.KOMFORT, 1, 60),
    ]
    assert logic.select_loads_to_shed(s, loads, LIMITS) == ["bluetti_laden"]


def test_lastabwurf_mehrere_und_nicht_abwerfbar():
    s = logic.resolve_sources(True, False, True)
    loads = [
        _load("induktion", Bus.PRIMAER, 6, 2000),
        _load("boiler", Bus.PRIMAER, 7, 1000),
        _load("shelly_wall", Bus.KOMFORT, 10, 5, sheddable=False),
        _load("steckdose", Bus.KOMFORT, 8, 300),
    ]
    # 3305 W bei 2300 W Grenze: Steckdose (8) und Boiler (7) reichen.
    assert logic.select_loads_to_shed(s, loads, LIMITS) == ["steckdose", "boiler"]


def test_lastabwurf_bluetti_nur_komfortbus():
    s = logic.resolve_sources(False, False, True)
    loads = [
        _load("induktion", Bus.PRIMAER, 10, 3000),
        _load("dusche", Bus.KOMFORT, 4, 2400),
    ]
    assert logic.select_loads_to_shed(s, loads, LIMITS) == ["dusche"]


def test_kein_abwurf_ohne_ueberlast():
    s = logic.resolve_sources(True, False, True)
    assert logic.select_loads_to_shed(s, [_load("x", Bus.KOMFORT, 5, 100)], LIMITS) == []


def test_verriegelung_letzter_gewinnt():
    pairs = [("switch.dusche", "switch.boiler")]
    assert logic.interlock_partners("switch.dusche", pairs, {"switch.boiler": True}) == [
        "switch.boiler"
    ]
    assert logic.interlock_partners("switch.boiler", pairs, {"switch.dusche": False}) == []
    assert logic.interlock_partners("switch.andere", pairs, {"switch.boiler": True}) == []
