"""Config flow to configure the Freebox integration."""

import logging
from typing import Any

from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .router import get_api, get_hosts_list_if_supported

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=80): vol.All(int, vol.Range(min=1, max=65535)),
    }
)


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle the Freebox config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}
        self._store: Store | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user.

        Args:
            user_input: User-provided configuration data, if any.

        Returns:
            ConfigFlowResult: The result of the configuration step.
        """
        self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)

        if user_input is None:
            stored_data = await self._store.async_load()
            if stored_data:
                _LOGGER.info("Restoring saved Freebox configuration for %s", stored_data.get(CONF_HOST))
                return await self.async_step_user(stored_data)
            return self.async_show_form(
                step_id="user",
                data_schema=DATA_SCHEMA,
                errors={},
            )

        self._data = user_input
        host = self._data[CONF_HOST]
        port = self._data[CONF_PORT]

        # Check if already configured
        await self.async_set_unique_id(host)
        self._abort_if_unique_id_configured()

        return await self.async_step_link()

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Attempt to link with the Freebox router.

        Prompts the user to authorize the connection on the Freebox device.

        Args:
            user_input: User confirmation, if any.

        Returns:
            ConfigFlowResult: The result of the linking step.
        """
        host = self._data[CONF_HOST]
        port = self._data[CONF_PORT]

        if user_input is None:
            return self.async_show_form(
                step_id="link",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "host": host,
                    "instructions": "Press the button on your Freebox to authorize the connection."
                },
                errors={},
            )

        errors = {}
        fbx = None
        try:
            fbx = await get_api(self.hass, host)
            await fbx.open(host, port)
            await fbx.system.get_config()  # Check permissions
            await get_hosts_list_if_supported(fbx)  # Additional validation

            # Save configuration
            if self._store:
                _LOGGER.info("Saving Freebox configuration for %s:%s", host, port)
                await self._store.async_save(self._data)

            return self.async_create_entry(title=host, data=self._data)

        except AuthorizationError as err:
            _LOGGER.error("Authorization failed for %s:%s - %s", host, port, str(err))
            errors["base"] = "register_failed"

        except HttpRequestError as err:
            _LOGGER.error("Connection failed for %s:%s - %s", host, port, str(err))
            errors["base"] = "cannot_connect"

        except Exception as err:
            _LOGGER.exception("Unknown error connecting to %s:%s", host, port)
            errors["base"] = "unknown"

        finally:
            if fbx:
                await fbx.close()

        return self.async_show_form(
            step_id="link",
            data_schema=vol.Schema({}),
            description_placeholders={
                "host": host,
                "instructions": "Press the button on your Freebox to authorize the connection."
            },
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a flow initiated by Zeroconf discovery.

        Args:
            discovery_info: Zeroconf service information.

        Returns:
            ConfigFlowResult: The result of the Zeroconf step.
        """
        properties = discovery_info.properties
        try:
            host = properties["api_domain"]
            port = int(properties["https_port"])
        except (KeyError, ValueError) as err:
            _LOGGER.warning("Invalid Zeroconf discovery data: %s", err)
            return self.async_abort(reason="invalid_zeroconf_data")

        _LOGGER.info("Discovered Freebox via Zeroconf at %s:%s", host, port)
        return await self.async_step_user({CONF_HOST: host, CONF_PORT: port})
