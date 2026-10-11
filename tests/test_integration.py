"""Integrationstests gegen einen echten Home-Assistant-Kern."""

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ca_camper.const import (
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
}


def _load(name, switch, bus, nominal, power=None):
    return {
        "name": name,
        "switch_entity": switch,
        "power_entity": power,
        "bus": bus,
        "nominal_w": nominal,
    }


OPTIONS = {
    CONF_LOADS: [
        _load("Induktion", "switch.induktion", "primaer", 3000, power="sensor.induktion_power"),
        _load("Boiler", "switch.boiler", "primaer", 1000),
        _load("DauerShower", "switch.dusche", "komfort", 2400),
        _load("Kühlschrank", "switch.kuehlschrank", "komfort", 60),
    ],
}


def _base_states(hass: HomeAssistant, landstrom="off", v2l="on", soc="80"):
    hass.states.async_set("binary_sensor.landstrom", landstrom)
    hass.states.async_set("binary_sensor.v2l", v2l)
    hass.states.async_set("sensor.generator_soc", soc)
    for sw in ("induktion", "boiler", "dusche", "kuehlschrank"):
        hass.states.async_set(f"switch.{sw}", "off")
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
    assert len(entry.options[CONF_LOADS]) == 5

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "remove_load"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"loads": ["switch.steckdose_heck"]}
    )
    await hass.async_block_till_done()
    assert len(entry.options[CONF_LOADS]) == 4


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

    hass.states.async_set("binary_sensor.landstrom", "on")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "landstrom"

    hass.states.async_set("binary_sensor.landstrom", "off")
    hass.states.async_set("binary_sensor.v2l", "off")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.ca_camper_primary_bus_source").state == "keine"
    assert hass.states.get("sensor.ca_camper_comfort_bus_source").state == "solargenerator"
    assert float(hass.states.get("sensor.ca_camper_power_limit").state) == 3600
    attrs = hass.states.get("binary_sensor.ca_camper_overload").attributes
    assert attrs["spannungslose_verbraucher"] == ["switch.induktion"]


async def test_overload_is_reported_but_nothing_is_switched(hass: HomeAssistant) -> None:
    calls: list[ServiceCall] = []

    async def _record(call: ServiceCall) -> None:
        calls.append(call)

    for domain, service in (("homeassistant", "turn_off"), ("switch", "turn_off")):
        hass.services.async_register(domain, service, _record)

    await _setup(hass, landstrom="on")  # 2300 W
    hass.states.async_set("switch.induktion", "on")
    hass.states.async_set("sensor.induktion_power", "2000")
    hass.states.async_set("switch.boiler", "on")
    hass.states.async_set("switch.dusche", "on")
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.ca_camper_overload").state == "on"
    assert hass.states.get("switch.boiler").state == "on"
    assert hass.states.get("switch.dusche").state == "on"
    assert calls == []


async def test_unload(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
