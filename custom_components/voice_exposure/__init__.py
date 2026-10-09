"""Expose and unexpose entities to voice assistants from scripts and automations.

Home Assistant keeps this setting per entity and per assistant, and only offers it
through the UI and an admin websocket command. These actions call the same helper
the websocket command does, so an automation can keep exposure in line with a rule,
such as "everything labeled voice".
"""

from __future__ import annotations

import logging
from typing import Any

try:  # Home Assistant moved from voluptuous to probatio in 2026.10.
    import probatio as vol
except ImportError:  # pragma: no cover
    import voluptuous as vol

from homeassistant.components.homeassistant.exposed_entities import (
    async_expose_entity,
    async_should_expose,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

_LOGGER = logging.getLogger(__name__)

DOMAIN = "voice_exposure"

# The ids Home Assistant uses for its assistants. "conversation" is Assist, which
# is also what custom conversation agents such as Jev read.
ASSISTANTS = ("conversation", "cloud.alexa", "cloud.google_assistant")

ATTR_ASSISTANTS = "assistants"
ATTR_DRY_RUN = "dry_run"
ATTR_ENTITY_ID = "entity_id"
ATTR_EXPOSE = "expose"
ATTR_UNEXPOSE_OTHERS = "unexpose_others"

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_ASSISTANTS_SCHEMA = vol.All(cv.ensure_list, [vol.In(ASSISTANTS)])

SET_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_EXPOSE): cv.boolean,
        vol.Optional(ATTR_ASSISTANTS, default=["conversation"]): _ASSISTANTS_SCHEMA,
        vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
    }
)

SYNC_SCHEMA = vol.Schema(
    {
        # A template that selects nothing renders as an empty string.
        vol.Required(ATTR_ENTITY_ID): vol.Any(
            vol.All(cv.string, vol.Length(max=0), lambda _: []), cv.entity_ids
        ),
        vol.Optional(ATTR_ASSISTANTS, default=["conversation"]): _ASSISTANTS_SCHEMA,
        vol.Optional(ATTR_UNEXPOSE_OTHERS, default=False): cv.boolean,
        vol.Optional(ATTR_DRY_RUN, default=True): cv.boolean,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions, which work as soon as the integration is added."""

    @callback
    def set_exposure(call: ServiceCall) -> ServiceResponse:
        entity_ids: list[str] = call.data[ATTR_ENTITY_ID]
        wanted: bool = call.data[ATTR_EXPOSE]
        changes = {
            assistant: _apply(
                hass,
                assistant,
                expose=entity_ids if wanted else [],
                unexpose=[] if wanted else entity_ids,
                dry_run=call.data[ATTR_DRY_RUN],
            )
            for assistant in call.data[ATTR_ASSISTANTS]
        }
        return {"dry_run": call.data[ATTR_DRY_RUN], "assistants": changes}

    @callback
    def sync_exposure(call: ServiceCall) -> ServiceResponse:
        desired: list[str] = call.data[ATTR_ENTITY_ID]
        unexpose_others: bool = call.data[ATTR_UNEXPOSE_OTHERS]
        # An empty selection with unexpose_others would unexpose the whole house,
        # which is far more often a broken template than an intention.
        if not desired and unexpose_others:
            raise ServiceValidationError(
                "entity_id is empty and unexpose_others is on, which would unexpose "
                "every entity. Use voice_exposure.set to unexpose on purpose."
            )
        wanted = set(desired)
        changes = {}
        for assistant in call.data[ATTR_ASSISTANTS]:
            others = (
                [
                    entity_id
                    for entity_id in hass.states.async_entity_ids()
                    if entity_id not in wanted
                ]
                if unexpose_others
                else []
            )
            changes[assistant] = _apply(
                hass,
                assistant,
                expose=sorted(wanted),
                unexpose=sorted(others),
                dry_run=call.data[ATTR_DRY_RUN],
            )
        return {"dry_run": call.data[ATTR_DRY_RUN], "assistants": changes}

    hass.services.async_register(
        DOMAIN,
        "set",
        set_exposure,
        schema=SET_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        "sync",
        sync_exposure,
        schema=SYNC_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to set up per entry. The entry only makes the actions load."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to unload."""
    return True


@callback
def _apply(
    hass: HomeAssistant,
    assistant: str,
    *,
    expose: list[str],
    unexpose: list[str],
    dry_run: bool,
) -> dict[str, Any]:
    """Change only what differs, and report what that was."""
    exposed: list[str] = []
    unexposed: list[str] = []
    unchanged = 0
    for entity_id, should in [(e, True) for e in expose] + [(e, False) for e in unexpose]:
        # The first read of an entity with no setting stores the default it already
        # had, as Assist itself does, so a dry run changes nothing that matters.
        if async_should_expose(hass, assistant, entity_id) == should:
            unchanged += 1
            continue
        (exposed if should else unexposed).append(entity_id)
        if not dry_run:
            async_expose_entity(hass, assistant, entity_id, should)
    if exposed or unexposed:
        _LOGGER.info(
            "%s %s: expose %s, unexpose %s",
            "Would change" if dry_run else "Changed",
            assistant,
            exposed,
            unexposed,
        )
    return {"exposed": exposed, "unexposed": unexposed, "unchanged": unchanged}
