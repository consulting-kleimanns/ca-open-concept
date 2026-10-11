"""Integrationstests gegen einen echten Home-Assistant-Kern."""

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.ca_camper.const import (
    CONF_CHARGE_SWITCH,
    CONF_GENERATOR_MIN_SOC,
    CONF_GENERATOR_SOC,
    CONF_LANDSTROM,
    CONF_LIMIT_GENERATOR,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_V2L,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """custom_components/ laden."""
    yield


DATA = {
    CONF_LANDSTROM: "binary_sensor.landstrom",
    CONF_V2L: "binary_sensor.v2l",
    CONF_GENERATOR_SOC: "sensor.generator_soc",
    CONF_GENERATOR_MIN_SOC: 10,
    CONF_LIMIT_LANDSTROM: 2300,
    CONF_LIMIT_V2L: 3500,
    CONF_LIMIT_GENERATOR: 3600,
    CONF_CHARGE_SWITCH: "input_boolean.laden",
}


def _load(name, switch, bus, nominal, power=None, flexible=False):
    return {
        "name": name,
        "switch_entity": switch,
        "power_entity": power,
        "bus": bus,
        "nominal_w": nominal,
        "flexible": flexible,
    }


OPTIONS = {
    CONF_LOADS: [
        _load(
            "Induktion", "input_boolean.induktion", "primaer", 3000, power="sensor.induktion_power"
        ),
        _load("Boiler", "input_boolean.boiler", "primaer", 1000, flexible=True),
        _load("DauerShower", "input_boolean.dusche", "komfort", 2400),
        _load("Kühlschrank", "input_boolean.kuehlschrank", "komfort", 60),
        _load("Laden", "input_boolean.laden", "primaer", 1500, flexible=True),
    ],
}


def _base_states(hass: HomeAssistant, landstrom="off", v2l="on", soc="80"):
    hass.states.async_set("binary_sensor.landstrom", landstrom)
    hass.states.async_set("binary_sensor.v2l", v2l)
    hass.states.async_set("sensor.generator_soc", soc)
    for sw in ("induktion", "boiler", "dusche", "kuehlschrank", "laden"):
        hass.states.async_set(f"input_boolean.{sw}", "off")
    hass.states.async_set("sensor.induktion_power", "0")


async def _setup(hass: HomeAssistant, **states) -> MockConfigEntry:
    _base_states(hass, **states)
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, options=OPTIONS, title="CA Camper")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_LIMIT_GENERATOR] == 3600


async def test_single_instance(hass: HomeAssistant) -> None:
    await _setup(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT


async def test_options_flow_add_and_remove_load(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_load"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "name": "Steckdose Heck",
            "switch_entity": "switch.steckdose_heck",
            "bus": "komfort",
            "nominal_w": 300,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(entry.options[CONF_LOADS]) == 6

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_load"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"loads": ["switch.steckdose_heck"]}
    )
    await hass.async_block_till_done()
    assert len(entry.options[CONF_LOADS]) == 5


async def test_sources_and_power(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "v2l"
    assert hass.states.get("sensor.ca_camper_comfort_bus_source").state == "solargenerator"
    assert float(hass.states.get("sensor.ca_camper_primary_bus_limit").state) == 3500
    assert float(hass.states.get("sensor.ca_camper_comfort_bus_limit").state) == 3600

    hass.states.async_set("input_boolean.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "1800")
    hass.states.async_set("input_boolean.kuehlschrank", "on")
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ca_camper_primary_bus_power").state) == 1800
    assert float(hass.states.get("sensor.ca_camper_comfort_bus_power").state) == 60
    assert float(hass.states.get("sensor.ca_camper_primary_bus_headroom").state) == 1700
    assert float(hass.states.get("sensor.ca_camper_comfort_bus_headroom").state) == 3540

    hass.states.async_set("binary_sensor.landstrom", "on")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "landstrom"

    hass.states.async_set("binary_sensor.landstrom", "off")
    hass.states.async_set("binary_sensor.v2l", "off")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "keine"
    assert hass.states.get("sensor.ca_camper_comfort_bus_source").state == "solargenerator"
    attrs = hass.states.get("binary_sensor.ca_camper_overload").attributes
    assert attrs["spannungslose_verbraucher"] == ["input_boolean.induktion"]


def _record_switch_calls(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def _record(call: ServiceCall) -> None:
        calls.append(call)
        state = "on" if call.service == "turn_on" else "off"
        ids = call.data["entity_id"]
        for entity_id in [ids] if isinstance(ids, str) else ids:
            hass.states.async_set(entity_id, state)

    for service in ("turn_on", "turn_off"):
        hass.services.async_register("input_boolean", service, _record)
    return calls


async def test_fixed_loads_are_never_switched(hass: HomeAssistant) -> None:
    calls = _record_switch_calls(hass)
    await _setup(hass, landstrom="on")  # 2300 W
    hass.states.async_set("input_boolean.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "3000")
    hass.states.async_set("input_boolean.dusche", "on")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.ca_camper_overload").state == "on"
    assert hass.states.get("input_boolean.induktion").state == "on"
    assert hass.states.get("input_boolean.dusche").state == "on"
    assert calls == []


async def test_reserve_load_paused_and_resumed(hass: HomeAssistant) -> None:
    calls = _record_switch_calls(hass)
    await _setup(hass)  # V2L 3500 W
    release = "binary_sensor.ca_camper_release_boiler"
    hass.states.async_set("input_boolean.boiler", "on")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "on"

    # Kochen: 3000 W Induktion -> Boiler hat keine Reserve mehr
    hass.states.async_set("input_boolean.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "3000")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "off"
    assert calls == []  # erst nach der Verzögerung
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert [c.service for c in calls] == ["turn_off"]
    assert hass.states.get("input_boolean.boiler").state == "off"
    assert hass.states.get(release).attributes["pausiert"] is True

    # Kochen beendet -> nach stabiler Reserve wieder an
    hass.states.async_set("input_boolean.induktion", "off")
    hass.states.async_set("sensor.induktion_power", "0")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert [c.service for c in calls] == ["turn_off", "turn_on"]
    assert hass.states.get("input_boolean.boiler").state == "on"
    assert hass.states.get(release).attributes["pausiert"] is False


async def test_auto_release_switch_off_disables_switching(hass: HomeAssistant) -> None:
    calls = _record_switch_calls(hass)
    await _setup(hass)
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.ca_camper_automatic_release"},
        blocking=True,
    )
    calls.clear()
    hass.states.async_set("input_boolean.boiler", "on")
    hass.states.async_set("input_boolean.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "3000")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ca_camper_release_boiler").state == "off"
    assert calls == []
    assert hass.states.get("input_boolean.boiler").state == "on"


async def test_charging_from_vehicle_only_below_threshold(hass: HomeAssistant) -> None:
    calls = _record_switch_calls(hass)
    await _setup(hass)  # V2L, Ladestand 80 %
    release = "binary_sensor.ca_camper_release_laden"
    hass.states.async_set("input_boolean.laden", "on")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "off"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.laden").state == "off"

    # Ladestand unter 30 % -> Laden aus der Fahrzeugbatterie
    hass.states.async_set("sensor.generator_soc", "25")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "on"
    assert hass.states.get(release).attributes["laden_aus_fahrzeug"] is True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert hass.states.get("input_boolean.laden").state == "on"

    # lädt weiter bis 80 %, dann Pause
    hass.states.async_set("sensor.generator_soc", "60")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "on"
    hass.states.async_set("sensor.generator_soc", "80")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "off"

    # Landstrom lädt jederzeit
    hass.states.async_set("binary_sensor.landstrom", "on")
    await hass.async_block_till_done()
    assert hass.states.get(release).state == "on"
    assert [c.service for c in calls] == ["turn_off", "turn_on"]


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
