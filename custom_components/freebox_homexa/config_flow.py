"""Flux de configuration pour l'intégration Freebox Homexa."""

import logging
from typing import Any

from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION
from .router import get_api, get_hosts_list_if_supported, resolve_token_file

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY_CONFIG = f"{DOMAIN}_config"

FREEBOX_ACCOUNTS_URL = "http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts"
FREEBOX_API_URL = "http://mafreebox.freebox.fr/api_version"

_PLACEHOLDERS = {
    "accounts_url": FREEBOX_ACCOUNTS_URL,
    "api_url": FREEBOX_API_URL,
}


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour l'intégration Freebox."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_CONFIG)
            stored_data = await store.async_load()
            if stored_data:
                user_input = stored_data
            else:
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_HOST): str,
                            vol.Required(CONF_PORT, default=80): int,
                        }
                    ),
                    description_placeholders=_PLACEHOLDERS,
                )

        self._data = user_input or {}
        await self.async_set_unique_id(self._data[CONF_HOST])
        if self.source != SOURCE_REAUTH:
            self._abort_if_unique_id_configured()
        return await self.async_step_link()

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Restart pairing when the Freebox token is missing or revoked."""
        self._data = dict(entry_data)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                description_placeholders=_PLACEHOLDERS,
            )
        return await self.async_step_link(user_input)

    async def _cleanup_invalid_token(self) -> None:
        try:
            token_file = resolve_token_file(self.hass, self._data.get(CONF_HOST, ""))
            if token_file.exists():
                await self.hass.async_add_executor_job(token_file.unlink)
        except Exception as err:
            _LOGGER.debug("Impossible de supprimer le token : %s", err)

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(
                step_id="link",
                description_placeholders=_PLACEHOLDERS,
            )

        errors = {}
        fbx = await get_api(self.hass, self._data[CONF_HOST])
        try:
            await fbx.open(
                self._data[CONF_HOST],
                self._data.get(CONF_PORT, 80),
            )

            await fbx.system.get_config()
            await get_hosts_list_if_supported(fbx)
            await fbx.close()

            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_CONFIG)
            await store.async_save(self._data)

            if self.source == SOURCE_REAUTH:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data=self._data,
                )

            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
            )

        except AuthorizationError as err:
            message = str(err).lower()
            if "denied" in message or "revoked" in message or "invalid" in message:
                _LOGGER.warning("Token Freebox révoqué : %s", err)
                await self._cleanup_invalid_token()
                errors["base"] = "invalid_token"
            else:
                _LOGGER.warning("Autorisation Freebox en attente / timeout, token conservé : %s", err)
                errors["base"] = "register_failed"

        except HttpRequestError:
            errors["base"] = "cannot_connect"

        except Exception:
            _LOGGER.exception("Erreur inconnue")
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="link",
            errors=errors,
            description_placeholders=_PLACEHOLDERS,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        host = discovery_info.properties.get("api_domain") or discovery_info.host
        port = discovery_info.properties.get("https_port") or 80
        return await self.async_step_user({CONF_HOST: host, CONF_PORT: int(port)})
