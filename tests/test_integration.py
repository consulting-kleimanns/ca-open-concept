"""Integrationstests gegen einen echten Home-Assistant-Kern."""

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.ca_camper.const import (
    CONF_BLUETTI_MIN_SOC,
    CONF_BLUETTI_SOC,
    CONF_INTERLOCKS,
    CONF_LANDSTROM,
    CONF_LIMIT_BLUETTI,
    CONF_LIMIT_LANDSTROM,
    CONF_LIMIT_V2L,
    CONF_LOADS,
    CONF_SHED_DELAY,
    CONF_V2L,
    DOMAIN,
    EVENT_INTERLOCK,
    EVENT_LOAD_SHED,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """custom_components/ laden."""
    yield


DATA = {
    CONF_LANDSTROM: "binary_sensor.landstrom",
    CONF_V2L: "binary_sensor.v2l",
    CONF_BLUETTI_SOC: "sensor.bluetti_soc",
    CONF_BLUETTI_MIN_SOC: 20,
    CONF_LIMIT_LANDSTROM: 2300,
    CONF_LIMIT_V2L: 3500,
    CONF_LIMIT_BLUETTI: 2200,
    CONF_SHED_DELAY: 3,
}


def _load(name, switch, bus, prio, nominal, power=None, sheddable=True):
    return {
        "id": name,
        "name": name,
        "switch_entity": switch,
        "power_entity": power,
        "bus": bus,
        "priority": prio,
        "nominal_w": nominal,
        "sheddable": sheddable,
    }


OPTIONS = {
    CONF_LOADS: [
        _load("Induktion", "switch.induktion", "primaer", 6, 3000, power="sensor.induktion_power"),
        _load("Boiler", "switch.boiler", "primaer", 7, 1000),
        _load("Bluetti laden", "switch.bluetti_laden", "primaer", 9, 500),
        _load("DauerShower", "switch.dusche", "komfort", 4, 2400),
        _load("Kühlschrank", "switch.kuehlschrank", "komfort", 1, 60),
        _load("Shelly Wall", "switch.shelly_wall", "komfort", 1, 5, sheddable=False),
    ],
    CONF_INTERLOCKS: [{"entity_a": "switch.dusche", "entity_b": "switch.boiler"}],
}


def _base_states(hass: HomeAssistant, landstrom="off", v2l="on", soc="80"):
    hass.states.async_set("binary_sensor.landstrom", landstrom)
    hass.states.async_set("binary_sensor.v2l", v2l)
    hass.states.async_set("sensor.bluetti_soc", soc)
    for sw in ("induktion", "boiler", "bluetti_laden", "dusche", "kuehlschrank", "shelly_wall"):
        hass.states.async_set(f"switch.{sw}", "off")
    hass.states.async_set("sensor.induktion_power", "0")


def _register_switch_services(hass: HomeAssistant) -> list[str]:
    """homeassistant.turn_off auf Testschalter umbiegen und Aufrufe protokollieren."""
    calls: list[str] = []

    async def _off(call: ServiceCall) -> None:
        for entity_id in (
            call.data["entity_id"]
            if isinstance(call.data["entity_id"], list)
            else [call.data["entity_id"]]
        ):
            calls.append(entity_id)
            hass.states.async_set(entity_id, "off")

    hass.services.async_register("homeassistant", "turn_off", _off)
    return calls


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
    assert result["data"][CONF_LIMIT_V2L] == 3500


async def test_single_instance(hass: HomeAssistant) -> None:
    await _setup(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT


async def test_options_flow_add_load(hass: HomeAssistant) -> None:
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
            "priority": 8,
            "nominal_w": 300,
            "sheddable": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(entry.options[CONF_LOADS]) == 7


async def test_sources_and_power(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "v2l"
    assert hass.states.get("sensor.ca_camper_comfort_bus_source").state == "v2l"
    assert float(hass.states.get("sensor.ca_camper_power_limit").state) == 3500

    hass.states.async_set("switch.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "1800")
    hass.states.async_set("switch.kuehlschrank", "on")
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.ca_camper_primary_bus_power").state) == 1800
    assert float(hass.states.get("sensor.ca_camper_comfort_bus_power").state) == 60
    assert float(hass.states.get("sensor.ca_camper_power_headroom").state) == 1640

    # Landstrom kommt -> Vorrang
    hass.states.async_set("binary_sensor.landstrom", "on")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "landstrom"

    # Alles weg -> Komfortbus auf Bluetti, Primärbus spannungslos
    hass.states.async_set("binary_sensor.landstrom", "off")
    hass.states.async_set("binary_sensor.v2l", "off")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "keine"
    assert hass.states.get("sensor.ca_camper_comfort_bus_source").state == "bluetti"
    attrs = hass.states.get("binary_sensor.ca_camper_overload").attributes
    assert attrs["spannungslose_verbraucher"] == ["switch.induktion"]


async def test_interlock_last_one_wins(hass: HomeAssistant) -> None:
    calls = _register_switch_services(hass)
    events = []
    hass.bus.async_listen(EVENT_INTERLOCK, events.append)
    await _setup(hass)

    hass.states.async_set("switch.boiler", "on")
    await hass.async_block_till_done()
    hass.states.async_set("switch.dusche", "on")
    await hass.async_block_till_done()

    assert calls == ["switch.boiler"]
    assert hass.states.get("switch.boiler").state == "off"
    assert events[0].data == {"turned_on": "switch.dusche", "turned_off": "switch.boiler"}


async def test_interlock_can_be_disabled(hass: HomeAssistant) -> None:
    calls = _register_switch_services(hass)
    await _setup(hass)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.ca_camper_interlock"}, blocking=True
    )
    hass.states.async_set("switch.boiler", "on")
    hass.states.async_set("switch.dusche", "on")
    await hass.async_block_till_done()
    assert calls == []


async def test_load_shedding_after_delay(hass: HomeAssistant) -> None:
    calls = _register_switch_services(hass)
    events = []
    hass.bus.async_listen(EVENT_LOAD_SHED, events.append)
    await _setup(hass, landstrom="on")  # 2300 W

    hass.states.async_set("switch.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "2000")
    hass.states.async_set("switch.bluetti_laden", "on")
    hass.states.async_set("switch.shelly_wall", "on")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.ca_camper_overload").state == "on"
    assert calls == []  # noch innerhalb der Verzögerung

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
    await hass.async_block_till_done()
    assert calls == ["switch.bluetti_laden"]
    assert hass.states.get("binary_sensor.ca_camper_overload").state == "off"
    assert events and events[0].data["entities"] == ["switch.bluetti_laden"]
    assert "Bluetti laden" in hass.states.get("sensor.ca_camper_last_action").state


async def test_short_peak_is_not_shed(hass: HomeAssistant) -> None:
    calls = _register_switch_services(hass)
    await _setup(hass, landstrom="on")
    hass.states.async_set("switch.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "2500")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.induktion_power", "1500")
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=4))
    await hass.async_block_till_done()
    assert calls == []


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
