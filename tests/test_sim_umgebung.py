"""Tests der Umgebungsauswertung (ohne Home Assistant, ohne Netz)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "sim_umgebung", Path(__file__).parents[1] / "demo/custom_components/ca_camper_sim/umgebung.py"
)
u = importlib.util.module_from_spec(_spec)
sys.modules["sim_umgebung"] = u
_spec.loader.exec_module(u)

LAT, LON = 48.0, 9.0


def _el(i, lat, lon, typ="node", center=False, **tags):
    pos = {"center": {"lat": lat, "lon": lon}} if center else {"lat": lat, "lon": lon}
    return {"type": typ, "id": i, "tags": tags, **pos}


def test_plz_und_ort():
    assert u.geocode_params("72070")["postalcode"] == "72070"
    assert u.geocode_params("Musterstadt am See")["q"] == "Musterstadt am See"


def test_abfrage_enthaelt_alle_kategorien():
    q = u.overpass_query(LAT, LON)
    assert q.count("out tags center") == len(u.KATEGORIEN)
    assert '"route"="hiking"' in q and "around:15000,48.00000,9.00000" in q


def test_auswertung_sortiert_und_beschreibt():
    data = {"elements": [
        _el(1, 48.05, 9.0, "relation", True, route="hiking", name="Panoramaweg", distance="12", network="lwn"),
        _el(2, 48.01, 9.0, "relation", True, route="hiking", name="Seerundweg"),
        _el(3, 48.01, 9.0, amenity="cafe", name="Hofcafé", cuisine="cake"),
        _el(4, 48.02, 9.0, amenity="charging_station", operator="Musterwerk", capacity="2"),
        _el(5, 48.0, 9.01, tourism="viewpoint"),
        _el(6, 48.0, 9.0, amenity="bench"),
        _el(7, 49.5, 9.0, amenity="restaurant", name="Viel zu weit"),
        _el(8, 48.01, 9.0, "relation", True, route="hiking", name="Seerundweg"),
    ]}
    r = u.auswerten(data, LAT, LON)
    assert [x["name"] for x in r["wandern"]] == ["Seerundweg", "Panoramaweg"]
    assert r["wandern"][1]["info"] == "12 km · lokal"
    assert r["wandern"][0]["link"] == "https://www.openstreetmap.org/relation/2"
    assert r["einkehren"][0]["info"] == "Café · cake"
    assert r["einkehren"] == r["einkehren"][:1]  # Restaurant außerhalb des Radius fällt weg
    assert r["laden"][0]["name"] == "Ladesäule Musterwerk"
    assert "2 Ladepunkte" in r["laden"][0]["info"]
    assert r["aussicht"][0]["name"] == "Aussichtspunkt"
    assert r["baden"] == [] and r["stellplatz"] == []
