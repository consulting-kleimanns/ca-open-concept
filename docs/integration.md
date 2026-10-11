# Home-Assistant-Integration „CA Camper Energiemanager“ (`ca_camper`)

Die Integration macht sichtbar, woher der Strom gerade kommt, wie viel Reserve bleibt, und warnt bei Überlast.
**Schalten darf sie nur Verbraucher „nur mit Reserve“** – im Open Concept der Boiler-Heizstab und das Laden des
Solargenerators. Feste Verbraucher (Induktion, DauerShower, Kühlschrank, Steckdosen …) schaltet sie nie.

## Entitäten

| Funktion | Entität (Name) |
|---|---|
| Quelle des Primärbusses (Landstrom → V2L) | Quelle Primärbus (Landstrom, V2L, Keine) |
| Quelle des Komfortbusses (Solargenerator → Primärbus) | Quelle Komfortbus (Solargenerator, Landstrom, V2L, Keine) |
| Leistung je Bus | Leistung Primärbus, Leistung Komfortbus |
| Grenze und Reserve je Bus | Grenze/Reserve Primärbus, Grenze/Reserve Komfortbus |
| Warnung, Attribut „spannungslose Verbraucher“ | Überlast |
| Freigabe je Verbraucher „nur mit Reserve“, Attribute „verbraucher“, „pausiert“ (beim Laden zusätzlich „laden_aus_fahrzeug“) | Freigabe ‹Name› |
| Automatisches Pausieren/Wiedereinschalten ein/aus (Vorgabe: ein) | Freigabesteuerung |

Alle Entitäten hängen am Gerät „CA Camper“; die Entitäts-IDs bildet Home Assistant aus den Namen in der Systemsprache.

**Leistungsbilanz:** Im Normalfall zwei unabhängige Kreise – der Primärbus hängt an Landstrom oder V2L, der Komfortbus am
Solargenerator; jeder Bus hat seine eigene Grenze und Reserve. Liegt der Solargenerator unter seiner Reserve, speist der
Primärbus laut VS2 auch den Komfortbus; dann teilen sich beide Busse dessen Grenze. Ohne Landstrom/V2L werden
eingeschaltete Primärbus-Verbraucher als „spannungslos“ gemeldet.

**Laden aus der Fahrzeugbatterie:** Der Verbraucher *Laden Solargenerator* lädt über V2L nur, wenn der Ladestand des
Solargenerators unter *Laden aus dem Fahrzeug unter* (Vorgabe 30 %) fällt, und dann bis *Laden aus dem Fahrzeug bis*
(Vorgabe 80 %). Über Landstrom lädt er jederzeit, sobald Reserve da ist. Den Schalter dafür einfach eingeschaltet lassen –
die Integration pausiert und startet ihn selbst.

**Freigabe nach Reserve:** Feste Verbraucher zählen mit ihrer aktuellen Leistung. Danach werden die Verbraucher
„nur mit Reserve“ in der Reihenfolge, in der sie angelegt wurden (= Priorität), hinzugenommen, solange
Last + Bedarf + Sicherheitsabstand die Grenze der Quelle nicht überschreiten. Ein laufender Verbraucher zählt mit seiner
Messung, ein ausgeschalteter mit seiner Nennleistung. Fehlt die Freigabe länger als die *Verzögerung Pause* (Vorgabe 2 s),
schaltet die Integration ihn aus und merkt ihn als „pausiert“; ist die Freigabe die *Verzögerung Wiederanlauf*
(Vorgabe 30 s) lang stabil, schaltet sie ihn wieder ein. Einen Reserve-Verbraucher einzuschalten heißt also „bei Bedarf
laufen lassen“ – die Integration sorgt dafür, dass er nur läuft, wenn Platz ist.

**Leistung eines Verbrauchers:** gemessene Leistung, wenn ein Leistungssensor zugeordnet ist, sonst die Nennleistung,
solange der Schalter an ist.

> ⚠️ Die Integration ersetzt keine elektrische Schutzeinrichtung.

## Installation

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/consulting-kleimanns/ca-open-concept`, Kategorie *Integration*.
2. „CA Camper Energiemanager“ installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → CA Camper Energiemanager*.

## Einrichtung

### Schritt 1: Quellen und Grenzen

| Feld | Was eintragen |
|---|---|
| Landstrom vorhanden | Binärsensor, der bei anliegendem Landstrom „an“ ist. Liefert dein Gerät nur eine Spannung, lege zuerst einen **Schwellenwert-Helfer** an (*Helfer → Schwellenwert*, z. B. über 200 V). |
| Fahrzeug-V2L aktiv | Binärsensor für die V2L-Einspeisung (ebenfalls z. B. über einen Schwellenwert-Helfer). |
| Ladestand Solargenerator | Batterie-Sensor (%) des Solargenerators, sofern eine Integration ihn liefert. |
| Reserve Solargenerator | Unter diesem Ladestand gilt der Solargenerator als nicht verfügbar. |
| Grenzen | Dauerleistung je Quelle. Vorgaben: Landstrom 2.300 W (10 A), V2L 3.700 W, Solargenerator 3.600 W (FOSSiBOT F3600 Pro) – **mit den Daten des eigenen Fahrzeugs und Geräts prüfen.** |
| Sicherheitsabstand | Reserve, die frei bleibt, bevor ein Reserve-Verbraucher freigegeben wird (Vorgabe 200 W). |
| Verzögerung Pause / Wiederanlauf | Vorgaben 2 s / 30 s. Die Pause-Verzögerung muss kürzer sein als die Überlastabschaltung der Quelle. |
| Laden Solargenerator | Schalter des Verbrauchers, der den Solargenerator lädt (als „nur mit Reserve“ anlegen). |
| Laden aus dem Fahrzeug unter / bis | Vorgaben 30 % / 80 % Ladestand des Solargenerators. |

### Schritt 2: Verbraucher (Optionen → Verbraucher hinzufügen)

Nach Elektroplan – Nennleistungen nach Datenblatt eintragen, besser einen Leistungssensor zuordnen.
Reserve-Verbraucher in der gewünschten Priorität anlegen (zuerst Boiler, dann Laden):

| ID | Verbraucher | Bus | Nur mit Reserve |
|---|---|---|---|
| AC-01 | Induktionskochfeld 3.000 W | Primär | nein |
| AC-02 | Boiler SafeBoil, Heizstab 1.000 W | Primär | **ja** |
| AC-03 | Laden Solargenerator (bis 2.200 W) | Primär | **ja** |
| AC-05 | DauerShower Durchlauferhitzer 2,4 kW | Komfort | nein |
| AC-06 | Kühlschrank | Komfort | nein |
| AC-07/08 | Steckdosen | Komfort | nein |
| AC-09 | Shelly Wall | Komfort | nein (Dauerversorgung) |
| – | Klimaanlage Truma Saphir | offen (Plan v6) | – |
| – | Infrarotpaneel 450 W | offen (Plan v6) | – |

Ladeleistung des Solargenerators am Gerät (App) auf einen Wert begrenzen, der zur Quelle passt, und diesen Wert als
Nennleistung eintragen.

## Beispiel: Benachrichtigung bei Überlast

Automation im UI anlegen: Auslöser *Entität → Zustand* auf „Überlast“ mit Zustand „an“ (z. B. für 5 Sekunden),
Aktion *Benachrichtigung senden*. Die Überlast-Warnung betrifft nur feste Verbraucher – Reserve-Verbraucher werden
vorher pausiert.

## Entwicklung

```bash
pip install pytest-homeassistant-custom-component ruff
pytest -q          # Logik- und Integrationstests gegen einen echten HA-Kern
ruff check custom_components tests
```

Die Bilanzlogik liegt ohne Home-Assistant-Abhängigkeit in `custom_components/ca_camper/logic.py`.
