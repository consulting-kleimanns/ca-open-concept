# Heizung und Klima (Entwurf) – CC BY-SA 4.0

## Konzept: hybrid

| Baustein | Gerät | Rolle | Steuerung |
|---|---|---|---|
| Klimaanlage | Truma Saphir (Staukasten, 230 V) | Kühlen; Heizen je nach Modell (siehe offene Punkte) | Truma-TIN-Bus, Anbindung über BlueBattery-System an Home Assistant (zu verifizieren) |
| Infrarot | Smart-Infrarotpaneel 450 W, Wand-/Deckenmontage (Könighaus M-Serie Smart) | Strahlungswärme, schnell und ohne Gebläse; Reserve bei jeder Außentemperatur | WLAN 2,4 GHz + App; Hersteller verlangt ein RF-Raumthermostat; Einbindung in Home Assistant zu prüfen |

Infrarot wärmt Körper und Oberflächen direkt statt der Raumluft. Man fühlt sich bei niedrigerer Lufttemperatur
wohl – das spart Energie. Die Tanks liegen im beheizten Innenraum.

## Bekannte Gerätedaten

- **Truma Saphir compact** (Händlerangabe): Kühlleistung 1.800 W, Nennstrom Kühlen 2,8 A (≈ 640 W bei 230 V,
  eigene Rechnung), Anlaufstrom 15 A für 150 ms, 230 V/50 Hz, IR-Fernbedienung, iNet X / iNet ready / CP plus,
  20 kg, für Fahrzeuge bis ca. 5,5 m. Eine Heizfunktion ist für dieses Modell beim Händler nicht genannt.
- **Infrarotpaneel M-Serie Smart 450 W** (Herstellerseite): Wand- und Deckenmontage, App und Raumthermostat
  parallel, nur 2,4-GHz-WLAN, RF-Raumthermostat zwingend, Festinstallation möglich, 1,80 m Kabel mit Stecker.

## Steuerung in Home Assistant

- **Truma über BlueBattery:** Das BlueBattery-BB-Display spricht über einen TIN-Adapter mit der Truma-Bedienung
  (CP plus iNet ready) und stellt Werte per MQTT bereit. Eine Community-Integration
  ([sahomm/BlueBattery](https://github.com/sahomm/BlueBattery), MIT) bindet das in Home Assistant ein. Dokumentiert ist
  dort die Truma-**Combi**-Heizung; ob die **Saphir**-Klimaanlage über denselben Weg steuerbar ist, wird am ersten
  Fahrzeug geprüft.
- **Infrarot:** Einbindung über die WLAN-Schnittstelle des Paneels; welche Integration passt, wird geprüft.
- **CA Camper Energiemanager:** Klimaanlage und Infrarot werden als Verbraucher mit Priorität eingetragen, damit sie
  bei knapper Leistung kontrolliert abgeworfen werden (z. B. Infrarot vor Kühlschrank).

## Offen

- Modell der Klimaanlage: Saphir **compact** (laut Händler nur Kühlen) oder Saphir **comfort RC** (Kühlen und Heizen).
- Einbindung von Klimaanlage und Infrarotpaneel in die Busstruktur (Primär- oder Komfortbus) – Elektroplan v6.
- Leistungsaufnahme beider Geräte im Betrieb am ersten Fahrzeug messen.
- Anlaufstrom der Klimaanlage gegen V2L- und Bluetti-Ausgang prüfen.
