# my-van – „Mein Master“ (Demo für Interessenten)

Interessenten erleben ihr Fahrzeug Monate vor der Auslieferung: Sie melden sich auf
**my-van.ca-camping.de** an (über login.ca-camping.de), bekommen ihre eigene Home-Assistant-Instanz
und richten Dashboards, Szenen und Automationen ein. Bei der Auslieferung wird alles ins Fahrzeug
übernommen.

| Ordner | Inhalt |
|---|---|
| `klickdummy/` | Statischer Klickdummy (läuft ohne Home Assistant) |
| `custom_components/ca_camper_sim/` | Simulation der Fahrzeugtechnik, auf der die echte Integration `ca_camper` läuft |
| `image/` | Docker-Image `ghcr.io/consulting-kleimanns/my-van-ha` (Home Assistant + Simulation + Dashboards) |

## Entity-Vertrag

Dashboards, Szenen und Automationen der Interessenten verwenden ausschließlich diese neutralen
Entity-IDs. In der Demo stellt sie `ca_camper_sim` bereit, im Fahrzeug werden die echten Geräte
(Shelly, Truma, Renault …) auf dieselben IDs umbenannt. Dadurch lässt sich alles 1:1 übernehmen.

| Bereich | Entity-IDs |
|---|---|
| 230-V-Kreise (je ein Shelly) | `switch.ac_02_boiler_heizstab`, `switch.ac_03_generator_1`, `switch.ac_03_generator_2`, `switch.ac_04_reserve_1`, `switch.ac_04_reserve_2`, `switch.ac_07_steckdose_heck`, `switch.ac_08_steckdose_trennwand`, `switch.reserve_3`, `switch.reserve_4` – Leistung jeweils `sensor.<name>_leistung` |
| Licht | `light.heck_links`, `light.heck_rechts`, `light.dusche` (dimmbar), `light.kueche` (Bewegung), `switch.kuechenlicht_automatik`, `binary_sensor.bewegung_kueche` |
| Wärme und Wasser | `climate.heizung` (Stufen eco/high), `climate.wandthermostat` (Infrarotheizung), `select.boiler` (Aus/Eco/High/Boost), `sensor.wasser_temperatur` |
| Raumklima | `sensor.innen_temperatur`, `sensor.innen_feuchte`, `sensor.taupunkt`, `sensor.aussentemperatur` |
| Energie | `binary_sensor.landstrom`, `binary_sensor.v2l`, `sensor.hausbatterie_1_ladestand`, `sensor.hausbatterie_2_ladestand`, `sensor.hausbatterie_ladestand`, `sensor.bordstrom_leistung`, `sensor.aussenstrom_leistung` |
| Fahrzeug | `sensor.fahrbatterie`, `sensor.reichweite`, `sensor.fahrzeug_energie`, `sensor.kilometerstand`, `sensor.ladezustand`, `sensor.stecker`, `sensor.ladeleistung`, `sensor.restladezeit`, `number.soll_ladestand`, `number.mindest_ladestand`, `button.vorklimatisieren`, `button.hupe`, `button.lichthupe`, `button.laden_starten`, `binary_sensor.klima_fahrerhaus` |
| Standort | `text.standort` (Ort oder PLZ; im Fahrzeug GPS) |
| Nur Demo | `select.sim_strom_vor_ort`, `select.sim_zeitraffer`, `button.sim_einsteigen`, `button.sim_kochen`, `button.sim_duschen`, `button.sim_kueche_betreten` |

Alle Werte der Simulation sind Musterwerte (`model.py`, Klasse `Params`).
