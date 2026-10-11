# CA Camping – Open Concept

Offener Standard für den **vollelektrischen Camper auf dem Renault Master E-Tech** (L2H2, 3,5 t):
Elektroplan, Wasseranlage, Heizung/Klima und eine Home-Assistant-Integration, die die Energielogik im Fahrzeug umsetzt.

🌐 Webseite: <https://open-concept.ca-camping.de/> · Werkstattverbund: <https://verbund.ca-camping.de/>

> **Status:** Planungsstand Oktober 2026, erstes Fahrzeug im Bau. Alles hier ist Entwurf und vor der Ausführung zu prüfen.

## Inhalt

| Bereich | Datei | Stand |
|---|---|---|
| Elektroplan (230 V, 12 V, 24 V, Solar) | [docs/elektrik.md](docs/elektrik.md) | Entwurf v5 |
| Wasseranlage | [docs/wasser.md](docs/wasser.md) | v9 |
| Heizung und Klima | [docs/heizung.md](docs/heizung.md) | Entwurf |
| Home-Assistant-Integration `ca_camper` | [custom_components/ca_camper](custom_components/ca_camper) · [Anleitung](docs/integration.md) | v0.1.0 |

![230-V-Quellenlogik](docs/diagrams/quellenlogik-230v.svg)

## Home-Assistant-Integration „CA Camper Energiemanager“

Die Integration steuert **keine Geräte direkt**. Sie nutzt Entitäten, die andere Integrationen bereits liefern
(Shelly-Schalter und -Leistungsmessung, Bluetti-Ladestand, Landstrom-/V2L-Erkennung, Truma über BlueBattery,
Infrarot-Paneel) und setzt darauf die Logik des Elektroplans um:

- **Vorrangschaltungen nachbilden:** Landstrom vor V2L → Primärbus; Primärbus vor Bluetti → Komfortbus
- **Leistung je Bus, Leistungsgrenze und Reserve** der aktiven Quelle
- **Verriegelung:** zwei Verbraucher nie gleichzeitig (z. B. DauerShower ↔ Boiler) – der zuletzt eingeschaltete gewinnt
- **Lastabwurf:** bei anhaltender Überlast werden Verbraucher nach Priorität abgeschaltet
- Ereignisse `ca_camper_load_shed` und `ca_camper_interlock` für eigene Automationen und Benachrichtigungen

Installation über HACS (benutzerdefiniertes Repository, Kategorie *Integration*), dann
**Einstellungen → Geräte & Dienste → Integration hinzufügen → CA Camper Energiemanager**.
Details: [docs/integration.md](docs/integration.md).

> ⚠️ Die Software-Verriegelung und der Lastabwurf **ersetzen keine elektrische Schutzeinrichtung**
> (Leitungsschutz, RCD, Umschalttechnik). Sie sind eine Komfort- und Effizienzfunktion.

## Mitmachen

Fehler gefunden, besseres Bauteil, eigener Nachbau? Issues und Pull Requests sind willkommen – siehe
[CONTRIBUTING.md](CONTRIBUTING.md). Werkstätten und Elektrofachkräfte: <https://verbund.ca-camping.de/>.

## Lizenzen

- **Dokumentation, Pläne, Tabellen, Diagramme** (`docs/`): © 2026 Jochen Kleimann / CA Camping – Open Concept,
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.de) – siehe [LICENSE-DOCS.md](LICENSE-DOCS.md).
- **Software** (`custom_components/`, `tests/`): [Apache License 2.0](LICENSE).
- Nicht lizenziert: Marke „CA Camping“, Logos, Fotos, die Bezeichnung „nach CA-Standard ausgebaut“,
  der Möbelgrundriss der Campermanufaktur Berlin.

Alle Inhalte werden ohne Gewähr bereitgestellt. Sie ersetzen weder Planung und Abnahme durch eine Elektrofachkraft
noch die Beachtung geltender Normen, Herstellerangaben und der Aufbaurichtlinien des Fahrzeugherstellers.
Genannte Marken (Renault, Home Assistant, Shelly, Bluetti, Truma, Dometic, DauerShower, Lilie, WM Aquatec, BlueBattery,
Könighaus u. a.) gehören ihren Inhabern und werden nur beschreibend genannt; eine Verbindung besteht nicht.

---

*English summary:* Open standard for a fully electric camper van based on the Renault Master E-Tech: wiring plan,
water system, heating, and a Home Assistant custom integration (`ca_camper`) that implements source priority,
per-bus power, interlocks and load shedding on top of existing entities. Docs CC BY-SA 4.0, code Apache-2.0.
