"""Config flow to configure the Freebox integration."""

import logging
from typing import Any

from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store  # Import du module de stockage

from .const import DOMAIN
from .router import get_api, get_hosts_list_if_supported

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}
        self._store = None  # Initialisation du stockage

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_PORT): int,
                    }
                ),
                errors={},
            )

        self._data = user_input

        # Check if already configured
        await self.async_set_unique_id(self._data[CONF_HOST])
        self._abort_if_unique_id_configured()

        # Charger les paramètres stockés si disponibles
        self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)
        stored_data = await self._store.async_load()

        if stored_data:
            _LOGGER.info("Restoring stored configuration data.")
            self._data.update(stored_data)

        return await self.async_step_link()

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Attempt to link with the Freebox router.

        Given a configured host, will ask the user to press the button
        to connect to the router.
        """
        if user_input is None:
            return self.async_show_form(step_id="link")

        errors = {}

        fbx = await get_api(self.hass, self._data[CONF_HOST])
        try:
            # Open connection and check authentication
            await fbx.open(self._data[CONF_HOST], self._data[CONF_PORT])

            # Check permissions
            await fbx.system.get_config()
            await get_hosts_list_if_supported(fbx)

            # Close connection
            await fbx.close()

            # Sauvegarder les paramètres après connexion réussie
            if self._store:
                await self._store.async_save(self._data)
                _LOGGER.info("Configuration data successfully saved.")

            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
            )

        except AuthorizationError as error:
            _LOGGER.error(error)
            errors["base"] = "register_failed"

        except HttpRequestError:
            _LOGGER.error(
                "Error connecting to the Freebox router at %s", self._data[CONF_HOST]
            )
            errors["base"] = "cannot_connect"

        except Exception:
            _LOGGER.exception(
                "Unknown error connecting with Freebox router at %s",
                self._data[CONF_HOST],
            )
            errors["base"] = "unknown"

        return self.async_show_form(step_id="link", errors=errors)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Initialize flow from zeroconf."""
        zeroconf_properties = discovery_info.properties
        host = zeroconf_properties["api_domain"]
        port = zeroconf_properties["https_port"]
        return await self.async_step_user({CONF_HOST: host, CONF_PORT: port})
