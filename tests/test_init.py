"""The set and sync actions."""

from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)
import yaml

from homeassistant.components.homeassistant.exposed_entities import (
    async_expose_entity,
    async_should_expose,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.setup import async_setup_component

from custom_components.voice_exposure import DOMAIN

EXAMPLES = Path(__file__).parent.parent / "examples"


def add(hass: HomeAssistant, entity_id: str, **kwargs) -> er.RegistryEntry:
    """A registered entity with a state, as an integration would leave it."""
    domain, object_id = entity_id.split(".")
    entry = er.async_get(hass).async_get_or_create(
        domain, "test", object_id, suggested_object_id=object_id, **kwargs
    )
    assert entry.entity_id == entity_id
    hass.states.async_set(entity_id, "off")
    return entry


def exposed(hass: HomeAssistant, *entity_ids: str) -> list[bool]:
    return [async_should_expose(hass, "conversation", e) for e in entity_ids]


async def call(hass: HomeAssistant, action: str, **data):
    return await hass.services.async_call(
        DOMAIN, action, data, blocking=True, return_response=True
    )


async def test_set_exposes_and_unexposes(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    add(hass, "light.ceiling")
    async_expose_entity(hass, "conversation", "light.desk", False)
    async_expose_entity(hass, "conversation", "light.ceiling", False)

    result = await call(hass, "set", entity_id=["light.desk"], expose=True)
    assert exposed(hass, "light.desk", "light.ceiling") == [True, False]
    assert result["assistants"]["conversation"] == {
        "exposed": ["light.desk"],
        "unexposed": [],
        "unchanged": 0,
    }

    await call(hass, "set", entity_id="light.desk", expose=False)
    assert exposed(hass, "light.desk") == [False]


async def test_set_dry_run_changes_nothing(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    async_expose_entity(hass, "conversation", "light.desk", False)

    result = await call(hass, "set", entity_id=["light.desk"], expose=True, dry_run=True)
    assert result["dry_run"] is True
    assert result["assistants"]["conversation"]["exposed"] == ["light.desk"]
    assert exposed(hass, "light.desk") == [False]


async def test_set_other_assistants_only(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    async_expose_entity(hass, "conversation", "light.desk", False)
    async_expose_entity(hass, "cloud.alexa", "light.desk", False)

    await call(hass, "set", entity_id=["light.desk"], expose=True, assistants="cloud.alexa")
    assert async_should_expose(hass, "cloud.alexa", "light.desk")
    assert exposed(hass, "light.desk") == [False]


async def test_sync_defaults_to_a_dry_run(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    add(hass, "light.ceiling")
    async_expose_entity(hass, "conversation", "light.desk", False)
    async_expose_entity(hass, "conversation", "light.ceiling", True)

    result = await call(hass, "sync", entity_id=["light.desk"], unexpose_others=True)
    assert result["assistants"]["conversation"] == {
        "exposed": ["light.desk"],
        "unexposed": ["light.ceiling"],
        "unchanged": 0,
    }
    assert exposed(hass, "light.desk", "light.ceiling") == [False, True]


async def test_sync_applies(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    add(hass, "light.ceiling")
    async_expose_entity(hass, "conversation", "light.desk", False)
    async_expose_entity(hass, "conversation", "light.ceiling", True)

    await call(hass, "sync", entity_id=["light.desk"], unexpose_others=True, dry_run=False)
    assert exposed(hass, "light.desk", "light.ceiling") == [True, False]

    again = await call(
        hass, "sync", entity_id=["light.desk"], unexpose_others=True, dry_run=False
    )
    assert again["assistants"]["conversation"]["exposed"] == []
    assert again["assistants"]["conversation"]["unexposed"] == []


async def test_sync_leaves_others_alone_by_default(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    add(hass, "light.ceiling")
    async_expose_entity(hass, "conversation", "light.desk", False)
    async_expose_entity(hass, "conversation", "light.ceiling", True)

    await call(hass, "sync", entity_id=["light.desk"], dry_run=False)
    assert exposed(hass, "light.desk", "light.ceiling") == [True, True]


async def test_sync_refuses_to_unexpose_everything(hass: HomeAssistant, loaded) -> None:
    add(hass, "light.desk")
    async_expose_entity(hass, "conversation", "light.desk", True)

    with pytest.raises(ServiceValidationError):
        await call(hass, "sync", entity_id=[], unexpose_others=True, dry_run=False)
    # A dry run may show what that would do.
    dry = await call(hass, "sync", entity_id=[], unexpose_others=True)
    assert dry["assistants"]["conversation"]["unexposed"] == ["light.desk"]
    # An empty template renders as "", which is accepted without unexpose_others.
    await call(hass, "sync", entity_id="", dry_run=False)
    assert exposed(hass, "light.desk") == [True]


async def test_only_one_entry(hass: HomeAssistant, loaded) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["title"] == "Voice exposure"


async def test_example_script(hass: HomeAssistant, loaded) -> None:
    """The example script exposes by label and keeps the unsafe ones out."""
    labels = lr.async_get(hass)
    voice = labels.async_create("voice").label_id
    no_voice = labels.async_create("no_voice").label_id
    office = ar.async_get(hass).async_create("Office", labels={voice})
    ar.async_get(hass).async_create("Kitchen")

    config_entry = MockConfigEntry(domain="test")
    config_entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    plug = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("test", "plug")}
    )
    devices.async_update_device(plug.id, area_id=office.id)
    sensor_device = devices.async_get_or_create(
        config_entry_id=config_entry.entry_id, identifiers={("test", "sensor")}
    )
    devices.async_update_device(sensor_device.id, labels={voice})

    entities = er.async_get(hass)
    add(hass, "light.office_ceiling")
    entities.async_update_entity("light.office_ceiling", area_id=office.id)
    add(hass, "switch.office_plug", device_id=plug.id)  # in the area by its device
    add(hass, "lock.office_door")
    entities.async_update_entity("lock.office_door", area_id=office.id)
    add(hass, "cover.office_garage")
    entities.async_update_entity("cover.office_garage", area_id=office.id)
    hass.states.async_set("cover.office_garage", "closed", {"device_class": "garage"})
    add(hass, "light.office_hidden")
    entities.async_update_entity(
        "light.office_hidden", area_id=office.id, hidden_by=er.RegistryEntryHider.USER
    )
    add(hass, "switch.office_led")
    entities.async_update_entity(
        "switch.office_led", area_id=office.id, labels={no_voice}
    )
    add(hass, "sensor.hall_temperature", device_id=sensor_device.id)
    add(hass, "light.kitchen")  # no label anywhere
    add(hass, "light.labeled")
    entities.async_update_entity("light.labeled", labels={voice})
    for entity_id in hass.states.async_entity_ids():
        async_expose_entity(hass, "conversation", entity_id, entity_id == "light.kitchen")

    notices = async_mock_service(hass, "persistent_notification", "create")
    scripts = yaml.safe_load((EXAMPLES / "script.yaml").read_text())
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()

    dry = await hass.services.async_call(
        "script", "sync_voice_exposure", {}, blocking=True, return_response=True
    )
    assert exposed(hass, "light.kitchen", "light.office_ceiling") == [True, False]
    assert sorted(dry["assistants"]["conversation"]["exposed"]) == [
        "light.labeled",
        "light.office_ceiling",
        "sensor.hall_temperature",
        "switch.office_plug",
    ]
    assert dry["assistants"]["conversation"]["unexposed"] == ["light.kitchen"]
    assert len(notices) == 1
    assert notices[0].data["title"] == "Voice exposure dry run"
    assert "Would expose (4): light.labeled, light.office_ceiling" in (
        notices[0].data["message"]
    )
    assert "Would unexpose (1): light.kitchen" in notices[0].data["message"]

    await hass.services.async_call(
        "script", "sync_voice_exposure", {"make_changes": True}, blocking=True, return_response=True
    )
    assert len(notices) == 2
    assert notices[1].data["title"] == "Voice exposure changed"
    assert exposed(
        hass,
        "light.labeled",
        "light.office_ceiling",
        "sensor.hall_temperature",
        "switch.office_plug",
    ) == [True, True, True, True]
    assert exposed(
        hass,
        "light.kitchen",
        "lock.office_door",
        "cover.office_garage",
        "light.office_hidden",
        "switch.office_led",
    ) == [False, False, False, False, False]


def test_example_automation_parses() -> None:
    automations = yaml.safe_load((EXAMPLES / "automation.yaml").read_text())
    assert automations[0]["actions"][-1]["action"] == "script.sync_voice_exposure"


async def test_example_script_with_nothing_labeled(hass: HomeAssistant, loaded) -> None:
    """Before any labels, a dry run shows everything would go, and nothing does."""
    lr.async_get(hass).async_create("voice")
    lr.async_get(hass).async_create("no_voice")
    add(hass, "light.desk")
    async_expose_entity(hass, "conversation", "light.desk", True)
    notices = async_mock_service(hass, "persistent_notification", "create")
    scripts = yaml.safe_load((EXAMPLES / "script.yaml").read_text())
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()

    await hass.services.async_call(
        "script", "sync_voice_exposure", {}, blocking=True, return_response=True
    )
    assert len(notices) == 1
    assert "Would expose (0): nothing" in notices[0].data["message"]
    assert "Would unexpose (1): light.desk" in notices[0].data["message"]
    assert exposed(hass, "light.desk") == [True]

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "script", "sync_voice_exposure", {"make_changes": True}, blocking=True,
            return_response=True,
        )
    assert exposed(hass, "light.desk") == [True]


async def test_example_script_reports_nothing_to_change(
    hass: HomeAssistant, loaded
) -> None:
    """A dry run with nothing to change still says so. A real run stays quiet."""
    voice = lr.async_get(hass).async_create("voice").label_id
    lr.async_get(hass).async_create("no_voice")
    add(hass, "light.desk")
    er.async_get(hass).async_update_entity("light.desk", labels={voice})
    async_expose_entity(hass, "conversation", "light.desk", True)
    notices = async_mock_service(hass, "persistent_notification", "create")
    scripts = yaml.safe_load((EXAMPLES / "script.yaml").read_text())
    assert await async_setup_component(hass, "script", {"script": scripts})
    await hass.async_block_till_done()
    for entity_id in hass.states.async_entity_ids("script"):
        async_expose_entity(hass, "conversation", entity_id, False)

    await hass.services.async_call(
        "script", "sync_voice_exposure", {}, blocking=True, return_response=True
    )
    assert len(notices) == 1
    assert "Would expose (0): nothing" in notices[0].data["message"]
    assert "Would unexpose (0): nothing" in notices[0].data["message"]

    await hass.services.async_call(
        "script", "sync_voice_exposure", {"make_changes": True}, blocking=True,
        return_response=True,
    )
    assert len(notices) == 1
