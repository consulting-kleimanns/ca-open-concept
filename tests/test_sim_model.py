"""Tests des Simulationsmodells (ohne Home Assistant)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sim_model", Path(__file__).parents[1] / "demo/custom_components/ca_camper_sim/model.py"
)
model = importlib.util.module_from_spec(_spec)
sys.modules["sim_model"] = model
_spec.loader.exec_module(model)

CamperModel, Standort, Boiler = model.CamperModel, model.Standort, model.Boiler


def test_v2l_liefert_nur_ueber_mindest_ladestand():
    m = CamperModel()
    assert m.v2l and m.limit_w == 3700
    m.s.car = 15
    assert not m.v2l and m.limit_w == 0


def test_landstrom_grenzen():
    m = CamperModel()
    m.set_standort(Standort.CAMPINGPLATZ_10A)
    assert m.landstrom and m.limit_w == 2300
    m.set_standort(Standort.CAMPINGPLATZ_16A)
    assert m.limit_w == 3600


def test_kochen_last_am_primaerbus_und_endet():
    m = CamperModel()
    m.s.circuits["ac_03_generator_1"] = False
    m.s.circuits["ac_03_generator_2"] = False
    m.s.boiler = Boiler.AUS
    m.kochen(2)
    assert m.tick(1).induktion_w == 3000
    m.tick(1)
    assert m.tick(1).induktion_w == 0


def test_duschen_entlaedt_hausbatterien():
    m = CamperModel()
    m.set_standort(Standort.CAMPINGPLATZ_16A)
    for c in m.s.circuits:
        m.s.circuits[c] = False
    vorher = m.eco_avg
    m.duschen(10)
    for _ in range(10):
        m.tick(1)
    assert m.eco_avg < vorher


def test_unter_reserve_kommt_bordstrom_von_aussen():
    m = CamperModel()
    m.s.eco = [15.0, 15.0]
    snap = m.snapshot()
    assert not snap.eco_ok
    assert snap.primaer_w >= snap.komfort_w


def test_boiler_heizt_bis_ziel():
    m = CamperModel()
    m.set_standort(Standort.CAMPINGPLATZ_16A)
    m.s.boiler = Boiler.ECO
    m.s.wasser = 40
    assert m.snapshot().boiler_heizt
    for _ in range(10):
        m.tick(1)
    assert m.s.wasser >= 44
    assert not m.snapshot().boiler_heizt


def test_kuechenlicht_per_bewegung_mit_nachlauf():
    m = CamperModel()
    assert not m.kuechenlicht
    m.kueche_betreten()
    assert m.kuechenlicht
    for _ in range(6):
        m.tick(1)
    assert not m.kuechenlicht
    m.s.kuechenlicht_auto = False
    m.kueche_betreten()
    assert not m.kuechenlicht


def test_laden_nur_an_der_wallbox():
    m = CamperModel()
    assert not m.laden_starten()
    m.set_standort(Standort.ZUHAUSE_WALLBOX)
    m.s.car = 50
    assert m.laden_starten()
    m.tick(30)
    assert m.s.car > 50 and m.restladezeit_min > 0
    m.set_standort(Standort.FREI_V2L)
    assert not m.s.car_charging


def test_v2l_zieht_aus_der_fahrzeugbatterie():
    m = CamperModel()
    m.kochen(10)
    vorher = m.s.car
    m.tick(10)
    assert m.s.car < vorher
