# Home-Assistant-Integration „CA Camper Energiemanager“ (`ca_camper`)

Die Integration **misst und zeigt an – sie schaltet nichts.** Beide 230-V-Kreise sind so ausgelegt, dass sie auch dann
unter ihrer Grenze bleiben, wenn alle Verbraucher gleichzeitig laufen. Die Integration macht sichtbar, woher der Strom
gerade kommt und wie viel Reserve bleibt, und warnt, falls die Auslegung im Betrieb doch nicht aufgeht.

## Entitäten

| Funktion | Entität (Name) |
|---|---|
| Quelle des Primärbusses (Landstrom → V2L) | Quelle Primärbus (Landstrom, V2L, Keine) |
| Quelle des Komfortbusses (Primärbus → Solargenerator) | Quelle Komfortbus (Landstrom, V2L, Solargenerator, Keine) |
| Leistung je Bus | Leistung Primärbus, Leistung Komfortbus |
| Grenze und Reserve der aktiven Quelle | Leistungsgrenze, Leistungsreserve |
| Warnung, Attribut „spannungslose Verbraucher“ | Überlast |

Alle Entitäten hängen am Gerät „CA Camper“; die Entitäts-IDs bildet Home Assistant aus den Namen in der Systemsprache.

**Leistungsbilanz:** Hat der Primärbus eine Quelle (Landstrom oder V2L), versorgt sie laut Vorrangschaltung VS2 auch den
Komfortbus – Grenze und Reserve beziehen sich dann auf beide Busse zusammen. Ohne Primärbus speist der Solargenerator
nur den Komfortbus; eingeschaltete Primärbus-Verbraucher werden als „spannungslos“ gemeldet.

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
| Grenzen | Dauerleistung je Quelle. Vorgaben: Landstrom 2.300 W (10 A), V2L 3.500 W, Solargenerator 3.600 W (FOSSiBOT F3600 Pro) – **mit den Daten des eigenen Fahrzeugs und Geräts prüfen.** |

### Schritt 2: Verbraucher (Optionen → Verbraucher hinzufügen)

Nach Elektroplan – Nennleistungen nach Datenblatt eintragen, besser einen Leistungssensor zuordnen:

| ID | Verbraucher | Bus |
|---|---|---|
| AC-01 | Induktionskochfeld 3.000 W | Primär |
| AC-02 | Boiler 230 V | Primär |
| AC-03 | Laden Solargenerator | Primär |
| AC-05 | DauerShower Durchlauferhitzer 2,4 kW | Komfort |
| AC-06 | Kühlschrank | Komfort |
| AC-07/08 | Steckdosen | Komfort |
| AC-09 | Shelly Wall | Komfort |
| – | Klimaanlage Truma Saphir | offen (Plan v6) |
| – | Infrarotpaneel 450 W | offen (Plan v6) |

## Beispiel: Benachrichtigung bei Überlast

Automation im UI anlegen: Auslöser *Entität → Zustand* auf „Überlast“ mit Zustand „an“ (z. B. für 5 Sekunden),
Aktion *Benachrichtigung senden*. Schlägt die Warnung im Betrieb an, stimmt die Auslegung oder eine Grenze nicht.

## Entwicklung

```bash
pip install pytest-homeassistant-custom-component ruff
pytest -q          # Logik- und Integrationstests gegen einen echten HA-Kern
ruff check custom_components tests
```

Die Bilanzlogik liegt ohne Home-Assistant-Abhängigkeit in `custom_components/ca_camper/logic.py`.
