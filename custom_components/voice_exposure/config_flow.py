"""Add the integration from the UI. There is nothing to configure."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from . import DOMAIN


class VoiceExposureConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry, which only makes the actions load."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Voice exposure", data={})
        return self.async_show_form(step_id="user")
