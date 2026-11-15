"""Umgebung des Standorts: Ort/PLZ → Koordinaten (Nominatim) → Ziele aus OpenStreetMap (Overpass).

Reine Funktionen für Abfrage und Auswertung (ohne Home Assistant testbar) plus ``async_suche``.
Im Fahrzeug kommen die Koordinaten später per GPS; die Auswertung bleibt gleich.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ca-camping-my-van/0.1 (+https://my-van.ca-camping.de)"
JE_KATEGORIE = 8


@dataclass(frozen=True)
class Kategorie:
    key: str
    name: str
    icon: str
    radius_m: int
    selektoren: tuple[str, ...]


KATEGORIEN: tuple[Kategorie, ...] = (
    Kategorie("wandern", "Wandern", "mdi:hiking", 15000,
              ('relation["route"="hiking"]["name"]',)),
    Kategorie("radtouren", "Radtouren", "mdi:bike", 15000,
              ('relation["route"="bicycle"]["name"]',)),
    Kategorie("aussicht", "Aussicht & Gipfel", "mdi:binoculars", 15000,
              ('node["tourism"="viewpoint"]', 'node["natural"="peak"]["name"]')),
    Kategorie("baden", "Baden", "mdi:swim", 15000,
              ('nwr["leisure"="bathing_place"]', 'nwr["leisure"="swimming_area"]',
               'nwr["natural"="beach"]["name"]')),
    Kategorie("einkehren", "Einkehren", "mdi:silverware-fork-knife", 5000,
              ('nwr["amenity"~"^(restaurant|cafe|biergarten)$"]["name"]',)),
    Kategorie("einkaufen", "Einkaufen", "mdi:cart", 6000,
              ('nwr["shop"~"^(supermarket|bakery|farm|butcher)$"]',)),
    Kategorie("laden", "Laden (E-Auto)", "mdi:ev-station", 10000,
              ('nwr["amenity"="charging_station"]',)),
    Kategorie("stellplatz", "Camping & Stellplätze", "mdi:caravan", 25000,
              ('nwr["tourism"~"^(camp_site|caravan_site)$"]',)),
)
KAT = {k.key: k for k in KATEGORIEN}

ART = {
    "restaurant": "Restaurant", "cafe": "Café", "biergarten": "Biergarten",
    "supermarket": "Supermarkt", "bakery": "Bäckerei", "farm": "Hofladen", "butcher": "Metzgerei",
    "camp_site": "Campingplatz", "caravan_site": "Wohnmobil-Stellplatz",
    "viewpoint": "Aussichtspunkt", "peak": "Gipfel", "bathing_place": "Badestelle",
    "swimming_area": "Badestelle", "beach": "Strand",
}
NETZ = {"lwn": "lokal", "rwn": "regional", "nwn": "national", "iwn": "international",
        "lcn": "lokal", "rcn": "regional", "ncn": "national", "icn": "international"}


def geocode_params(ort: str) -> dict[str, str]:
    """Parameter für Nominatim; eine fünfstellige Zahl gilt als deutsche PLZ."""
    ort = ort.strip()
    base = {"format": "jsonv2", "limit": "1", "accept-language": "de", "addressdetails": "0"}
    if re.fullmatch(r"\d{5}", ort):
        return {**base, "postalcode": ort, "countrycodes": "de"}
    return {**base, "q": ort}


def overpass_query(lat: float, lon: float) -> str:
    """Eine Abfrage, je Kategorie ein eigener Ausgabeblock (begrenzt)."""
    teile = ["[out:json][timeout:25];"]
    for k in KATEGORIEN:
        sel = "".join(f"{s}(around:{k.radius_m},{lat:.5f},{lon:.5f});" for s in k.selektoren)
        teile.append(f"({sel});out tags center 80;")
    return "".join(teile)


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def kategorie(tags: dict[str, str]) -> str | None:
    route = tags.get("route")
    if route == "hiking":
        return "wandern"
    if route == "bicycle":
        return "radtouren"
    if tags.get("tourism") == "viewpoint" or tags.get("natural") == "peak":
        return "aussicht"
    if tags.get("leisure") in ("bathing_place", "swimming_area") or tags.get("natural") == "beach":
        return "baden"
    if tags.get("amenity") in ("restaurant", "cafe", "biergarten"):
        return "einkehren"
    if tags.get("shop") in ("supermarket", "bakery", "farm", "butcher"):
        return "einkaufen"
    if tags.get("amenity") == "charging_station":
        return "laden"
    if tags.get("tourism") in ("camp_site", "caravan_site"):
        return "stellplatz"
    return None


def _info(key: str, t: dict[str, str]) -> str:
    teile: list[str] = []
    if key in ("wandern", "radtouren"):
        if d := t.get("distance"):
            teile.append(f"{d.replace(' km', '').replace('km', '').strip()} km")
        if n := NETZ.get(t.get("network", "")):
            teile.append(n)
    elif key == "aussicht":
        teile.append(ART.get(t.get("tourism") or t.get("natural", ""), ""))
        if e := t.get("ele"):
            teile.append(f"{e.split('.')[0]} m")
    elif key == "einkehren":
        teile.append(ART.get(t.get("amenity", ""), ""))
        if c := t.get("cuisine"):
            teile.append(c.replace("_", " ").replace(";", ", "))
    elif key == "einkaufen":
        teile.append(ART.get(t.get("shop", ""), ""))
    elif key == "laden":
        if c := t.get("capacity"):
            teile.append(f"{c} Ladepunkte")
        if t.get("socket:type2_combo") or t.get("socket:ccs"):
            teile.append("CCS")
        if o := t.get("operator"):
            teile.append(o)
    elif key == "stellplatz":
        teile.append(ART.get(t.get("tourism", ""), ""))
        if t.get("power_supply") == "yes":
            teile.append("Strom")
    elif key == "baden":
        teile.append(ART.get(t.get("leisure") or t.get("natural", ""), ""))
    return " · ".join(x for x in teile if x)


def _name(key: str, t: dict[str, str]) -> str | None:
    name = t.get("name") or t.get("brand")
    if name:
        return name
    if key == "laden":
        return f"Ladesäule {t['operator']}" if t.get("operator") else "Ladesäule"
    if key in ("aussicht", "baden", "einkaufen"):
        return ART.get(t.get("tourism") or t.get("leisure") or t.get("shop") or t.get("natural", ""))
    return None


def auswerten(data: dict[str, Any], lat: float, lon: float) -> dict[str, list[dict[str, Any]]]:
    """Overpass-Antwort → je Kategorie die nächsten Ziele (Name, km, Info, Link, Koordinaten)."""
    out: dict[str, list[dict[str, Any]]] = {k.key: [] for k in KATEGORIEN}
    gesehen: dict[str, set[str]] = {k.key: set() for k in KATEGORIEN}
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        key = kategorie(tags)
        if not key:
            continue
        pos = el.get("center") or el
        if "lat" not in pos:
            continue
        name = _name(key, tags)
        if not name:
            continue
        dist = km(lat, lon, pos["lat"], pos["lon"])
        if dist * 1000 > KAT[key].radius_m * 1.3:
            continue
        ident = f"{name.lower()}|{round(dist, 1)}" if key == "laden" else name.lower()
        if ident in gesehen[key]:
            continue
        gesehen[key].add(ident)
        out[key].append({
            "name": name,
            "km": round(dist, 1),
            "info": _info(key, tags),
            "lat": round(pos["lat"], 5),
            "lon": round(pos["lon"], 5),
            "link": f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
        })
    for key in out:
        out[key] = sorted(out[key], key=lambda x: x["km"])[:JE_KATEGORIE]
    return out


async def async_suche(session, ort: str) -> dict[str, Any]:  # noqa: ANN001 – aiohttp.ClientSession
    """Ort suchen und Umgebung abfragen. Wirft bei Netzfehlern; liefert ``gefunden=False`` ohne Treffer."""
    import aiohttp  # erst hier: die reinen Funktionen bleiben ohne aiohttp testbar

    hdr = {"User-Agent": USER_AGENT, "Accept-Language": "de"}
    async with session.get(NOMINATIM, params=geocode_params(ort), headers=hdr,
                           timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        treffer = await r.json(content_type=None)
    if not treffer:
        return {"ort": ort, "gefunden": False}
    t = treffer[0]
    lat, lon = float(t["lat"]), float(t["lon"])
    async with session.post(
        OVERPASS, data={"data": overpass_query(lat, lon)}, headers=hdr, timeout=aiohttp.ClientTimeout(total=45)
    ) as r:
        r.raise_for_status()
        data = await r.json(content_type=None)
    return {
        "ort": ort,
        "gefunden": True,
        "anzeige": t.get("display_name", ort),
        "lat": round(lat, 5),
        "lon": round(lon, 5),
        "kategorien": auswerten(data, lat, lon),
    }
