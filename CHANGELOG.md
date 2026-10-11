# Changelog

## 0.3.0 – 2026-10-11

### Neu
- **Freigabe nach Reserve:** Verbraucher können als „nur mit Reserve“ markiert werden (Boiler-Heizstab, Laden Solargenerator).
  Sie erhalten je einen Binärsensor „Freigabe ‹Name›“ und werden ohne Reserve pausiert und danach automatisch wieder eingeschaltet.
- Schalter „Freigabesteuerung“ (Zustand bleibt über Neustarts), Optionen Sicherheitsabstand (200 W), Verzögerung Pause (2 s) und Wiederanlauf (30 s).
- Feste Verbraucher werden weiterhin nie geschaltet.

### Dokumentation
- Elektroplan: Boiler und Laden laufen nur mit Reserve; offener Punkt Leistungsbilanz der festen Verbraucher (Induktion am Landstrom, Induktion + DauerShower an V2L).

## 0.2.0 – 2026-10-11

### Geändert
- Integration misst und zeigt nur noch an: **Verriegelung und Lastabwurf entfernt** (Auslegung: beide Kreise bleiben auch bei Volllast unter ihrer Grenze).
- Solargenerator statt „Bluetti“: Optionen `generator_soc_entity`, `generator_min_soc`, `limit_generator_w` (Vorgabe 3.600 W, z. B. FOSSiBOT F3600 Pro).
- Entfernt: Schalter Lastmanagement/Verriegelung, Sensor „Letzte Aktion“, Ereignisse `ca_camper_load_shed`/`ca_camper_interlock`, Priorität und „abwerfbar“ bei Verbrauchern.
- Überlast-Binärsensor bleibt als reine Warnung.

### Dokumentation
- Elektroplan: Verriegelung DauerShower ↔ Boiler entfällt, Solargenerator FOSSiBOT F3600 Pro.
- Boiler PEKAWAY SafeBoil 10 l (230 V/1.000 W + 12 V/200 W); Solargenerator lädt über Solar, bei Bedarf über Landstrom/Fahrzeug.

## 0.1.0 – 2026-10-11

### Integration `ca_camper`
- Einrichtung per UI: Quellen (Landstrom, V2L, Bluetti-Ladestand), Grenzen, Verzögerung
- Optionen: Verbraucher mit Bus, Priorität, Nennleistung, Leistungssensor; Verriegelungen
- Sensoren: Quelle je Bus, Leistung je Bus, Grenze, Reserve, letzte Aktion; Binärsensor Überlast
- Verriegelung (letzter gewinnt) und Lastabwurf nach Priorität mit Verzögerung
- Schalter für Lastmanagement und Verriegelung (Zustand bleibt über Neustarts)
- 21 Tests (Logik + Home-Assistant-Kern 2026.2)

### Dokumentation
- Elektroplan Entwurf v5, Wasseranlage v9, Heizung/Klima Entwurf (CC BY-SA 4.0)
