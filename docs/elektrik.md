# Elektroplan (Entwurf v5, 06.07.2026) – CC BY-SA 4.0

![230-V-Quellenlogik](diagrams/quellenlogik-230v.svg)

## 230-V-Quellenlogik
- VS1: Landstrom (Prio 1) vor Fahrzeug-V2L (Prio 2) → Primärbus
- Primärbus: Induktion 3.000 W (AC-01), Boiler SafeBoil 10 l mit Heizstab 230 V/1.000 W (AC-02, bei Bedarf), Laden Solargenerator (AC-03, bei Bedarf)
- VS2: Primärbus (Prio 1) vor Ausgang Solargenerator (Prio 2) → Komfortbus
- Komfortbus: DauerShower 2.0 Durchlauferhitzer ≤ 2,4 kW (AC-05), Kühlschrank Dometic RC10.4T.70 (AC-06), Steckdosen Heck (AC-07) und Trennwand (AC-08), Shelly Wall (AC-09, Dauerversorgung)
- Solar: Dach → DC-Trennstelle/Sicherung → MPPT-Eingang des Solargenerators; keine Verbindung zur 230-V-Verteilung
- Laden: Der Solargenerator lädt über Solar, bei Bedarf zusätzlich über Landstrom oder Fahrzeug (AC-03). Der Boiler heizt mit Solarüberschuss, bei Bedarf mit dem 1.000-W-Heizstab (AC-02).
- Jeder Verbraucher eigener Shelly-Kanal, Messung und Szenen in Home Assistant; kein zusätzliches Lastrelais
- **Freigabe nach Reserve:** Boiler-Heizstab (AC-02) und Laden des Solargenerators (AC-03) laufen nur, solange die speisende Quelle sie zusätzlich trägt (Sicherheitsabstand 200 W). Sonst pausiert Home Assistant sie und schaltet sie wieder ein, sobald die Reserve stabil reicht. Reihenfolge: erst Boiler, dann Laden.
- **Feste Verbraucher** (Induktion, DauerShower, Kühlschrank, Steckdosen, Shelly Wall) werden nie geschaltet. Die Verriegelung DauerShower ↔ Boiler aus Entwurf v5 entfällt.

## Solargenerator
FOSSiBOT F3600 Pro: 3.840 Wh, 3.600 W AC-Dauerleistung (3 × 230 V), AC-Laden bis 2.200 W, Solar bis 2.000 W, USV-Umschaltung 10 ms, 37,8 kg (Herstellerangaben laut Presse).

## 12 V DC
DC12-01 DauerShower 12 V (10 A, Sicherung typ. 15 A) · DC12-02 Pumpe Dusche/Abwasser (5–10 A) · DC12-03 Frischwasserpumpe (10 A) ·
DC12-04 E-Kugelhahn Abwasser (3–5 A) · DC12-05 Trittstufe (15–20 A, Tür-/Fahrfreigabe) · DC12-06 Dachlüfter (10 A) ·
DC12-07 Mischarmatur-Mikroschalter (1–3 A, keine 230-V-Last)

## 24 V DC
DC24-Q Wandler + Sicherungsblock · DC24-01…04 LED-Lichtbänder je Zone, Shelly-Dimmkanal

## Solar
PV-01 Dachmodule · PV-02 Dachdurchführung · PV-03 DC-Trennstelle + Sicherung · PV-04 MPPT-Eingang Solargenerator

## Checkliste
- Shelly-Modelle je Abgang nach Dauerstrom, Einschaltstrom, AC/DC-Eignung und Einbauart auswählen.
- RCD/FI, Leitungsschutz, Schutzleiter, Potentialausgleich, Netzform und Umschalttechnik durch die Elektrofachkraft festlegen.
- AC- und DC-Leitungen räumlich getrennt verlegen; Kreuzungen kurz und rechtwinklig; Durchführungen mit Kantenschutz und Zugentlastung.
- Jede Leitung an beiden Enden mit ihrer ID beschriften.
- DauerShower doppelt einplanen: AC-05 (Durchlauferhitzer) und DC12-01/02 (12 V, Pumpe).
- Shelly Wall so versorgen, dass sie nicht durch eine Szene spannungslos wird.
- Eingang, Ausgang und Solareingang des Solargenerators physisch und in der Beschriftung trennen.
- Mischarmatur nur über 12-V-Mikroschalter anschließen – keine 230-V-Zuleitung.
- Anschlussart des Kühlschranks am gelieferten Gerät prüfen.

## Offen
- 12-V-Quelle (Netzteil oder Batteriebezug)
- Kühlschrank-Anschlussart
- Shelly-Modelle je Abgang
- Boiler mit Solarüberschuss: Anschluss und Steuerung des 12-V-Heizstabs (200 W) bzw. Überschussregelung
- Leistungsbilanz der festen Verbraucher je Quelle: Induktion 3.000 W liegt allein über Landstrom 10 A (2.300 W); Induktion + DauerShower (5.400 W) liegen über V2L (3.500 W), solange der Komfortbus über VS2 am Primärbus hängt
- Einbindung Klimaanlage und Infrarotpaneel (siehe [heizung.md](heizung.md)) – Plan v6
- Möbellayout: Plan basiert auf dem Grundriss „Kompakter Allrounder“ (Variante für Boxer/Ducato L2); Anpassung an den Master wird dokumentiert
