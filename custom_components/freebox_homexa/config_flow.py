"""Flux de configuration Freebox Homexa."""

import logging
from typing import Any

from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .router import get_api

_LOGGER = logging.getLogger(__name__)
STORAGE_KEY_CONFIG = f"{DOMAIN}_config"


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gestion du flux de configuration."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=80): int,
                }),
            )

        self._data = user_input
        await self.async_set_unique_id(self._data[CONF_HOST])
        self._abort_if_unique_id_configured()
        return await self.async_step_link()

    async def async_step_link(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="link")

        errors = {}
        try:
            port = self._data.get(CONF_PORT, 80)
            fbx = await get_api(self.hass, self._data[CONF_HOST], port)

            await fbx.system.get_config()
            await fbx.close()

            # Sauvegarde
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_CONFIG)
            await store.async_save(self._data)

            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
            )

        except AuthorizationError:
            errors["base"] = "invalid_token"
        except HttpRequestError:
            errors["base"] = "cannot_connect"
        except Exception as err:
            _LOGGER.exception("Erreur inconnue")
            errors["base"] = "unknown"

        return self.async_show_form(step_id="link", errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Support découverte automatique."""
        host = discovery_info.properties.get("api_domain") or discovery_info.host
        port = discovery_info.properties.get("https_port") or 80
        return await self.async_step_user({CONF_HOST: host, CONF_PORT: int(port)})
