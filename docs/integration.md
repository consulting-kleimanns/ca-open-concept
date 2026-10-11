# Home-Assistant-Integration „CA Camper Energiemanager“ (`ca_camper`)

## Was sie macht

| Funktion | Entität (Name) |
|---|---|
| Quelle des Primärbusses (Landstrom → V2L) | Quelle Primärbus (Landstrom, V2L, Keine) |
| Quelle des Komfortbusses (Primärbus → Bluetti) | Quelle Komfortbus |
| Leistung je Bus | Leistung Primärbus, Leistung Komfortbus |
| Grenze und Reserve der aktiven Quelle | Leistungsgrenze, Leistungsreserve |
| Überlast (Attribut: spannungslose Verbraucher) | Überlast |
| Letzte Verriegelung/Lastabwurf | Letzte Aktion |
| Lastmanagement und Verriegelung an/aus | Lastmanagement, Verriegelung |

Alle Entitäten hängen am Gerät „CA Camper“; die Entitäts-IDs bildet Home Assistant aus den Namen in der Systemsprache.

**Leistungsbilanz:** Hat der Primärbus eine Quelle (Landstrom oder V2L), hängen beide Busse daran und teilen sich deren
Grenze. Ohne Primärbus speist die Bluetti nur den Komfortbus; eingeschaltete Primärbus-Verbraucher werden als
„spannungslos“ gemeldet.

**Leistung eines Verbrauchers:** gemessene Leistung, wenn ein Leistungssensor zugeordnet ist, sonst die Nennleistung,
solange der Schalter an ist.

**Lastabwurf:** Liegt die Last länger als die eingestellte Verzögerung (Standard 3 s) über der Grenze, werden
eingeschaltete, abwerfbare Verbraucher abgeschaltet – höchste Prioritätszahl zuerst, bei Gleichstand der größte – bis die
Grenze eingehalten ist. Abgeworfene Verbraucher werden **nicht** automatisch wieder eingeschaltet.

**Verriegelung:** Wird einer von zwei verriegelten Verbrauchern eingeschaltet, schaltet die Integration den anderen aus.

> ⚠️ Beides ersetzt keine elektrische Schutzeinrichtung.

## Installation

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/consulting-kleimanns/ca-open-concept`, Kategorie *Integration*.
2. „CA Camper Energiemanager“ installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → CA Camper Energiemanager*.

## Einrichtung

### Schritt 1: Quellen und Grenzen

| Feld | Was eintragen |
|---|---|
| Landstrom vorhanden | Binärsensor, der bei anliegendem Landstrom „an“ ist. Liefert dein Gerät nur eine Spannung, lege zuerst einen **Schwellenwert-Helfer** an (*Helfer → Schwellenwert*, z. B. über 200 V). |
| Fahrzeug-V2L aktiv | Binärsensor für die V2L-Einspeisung (ebenfalls z. B. über einen Schwellenwert-Helfer auf eine Spannungsmessung). |
| Ladestand Bluetti | Batterie-Sensor (%) aus der Bluetti-Integration deiner Wahl. |
| Reserve Bluetti | Unter diesem Ladestand gilt die Bluetti als nicht verfügbar. |
| Grenzen | Dauerleistung je Quelle. Vorgaben: Landstrom 2.300 W (10 A), V2L 3.500 W, Bluetti 2.200 W – **mit den Daten des eigenen Fahrzeugs und Geräts prüfen.** |

### Schritt 2: Verbraucher (Optionen → Verbraucher hinzufügen)

Vorschlag nach Elektroplan v5 – Nennleistungen nach Datenblatt anpassen:

| ID | Verbraucher | Bus | Priorität | Abwerfbar |
|---|---|---|---|---|
| AC-01 | Induktionskochfeld | Primär | 6 | ja |
| AC-02 | Boiler 230 V | Primär | 7 | ja |
| AC-03 | Bluetti laden | Primär | 9 | ja |
| AC-05 | DauerShower Durchlauferhitzer | Komfort | 4 | ja |
| AC-06 | Kühlschrank | Komfort | 2 | ja |
| AC-07/08 | Steckdosen | Komfort | 8 | ja |
| AC-09 | Shelly Wall | Komfort | 1 | **nein** |
| – | Klimaanlage Truma Saphir | offen (Plan v6) | 5 | ja |
| – | Infrarotpaneel 450 W | offen (Plan v6) | 6 | ja |

Priorität 1 = wird zuletzt abgeworfen, 10 = zuerst.

### Schritt 3: Verriegelungen (Optionen → Verriegelung hinzufügen)

- DauerShower (AC-05) ↔ Boiler (AC-02) – laut Elektroplan nie gleichzeitig.

## Beispiel: Benachrichtigung bei Lastabwurf

Automation im UI anlegen, Auslöser *Ereignis* mit Ereignistyp `ca_camper_load_shed`, Aktion *Benachrichtigung senden*
mit dem Zustand der Entität „Letzte Aktion“.

## Entwicklung

```bash
pip install pytest-homeassistant-custom-component ruff
pytest -q          # Logik- und Integrationstests gegen einen echten HA-Kern
ruff check custom_components tests
```

Die Entscheidungslogik liegt ohne Home-Assistant-Abhängigkeit in `custom_components/ca_camper/logic.py`.
