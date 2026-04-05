"""Flux de configuration pour l'intégration Freebox dans Home Assistant."""

import logging
from typing import Any
from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify
from pathlib import Path

from .const import DOMAIN, STORAGE_VERSION
from .router import get_api, get_hosts_list_if_supported

_LOGGER = logging.getLogger(__name__)

# Clé de stockage différente pour éviter le conflit avec le dossier des tokens
STORAGE_KEY_CONFIG = f"{DOMAIN}_config"


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour l'intégration Freebox."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape utilisateur."""
        if user_input is None:
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_CONFIG)
            stored_data = await store.async_load()
            if stored_data:
                _LOGGER.info("Configuration Freebox précédente restaurée.")
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
                    errors={},
                )

        self._data = user_input or {}
        await self.async_set_unique_id(self._data[CONF_HOST])
        self._abort_if_unique_id_configured()
        return await self.async_step_link()

    async def _cleanup_invalid_token(self) -> None:
        """Nettoyage automatique du token invalide."""
        try:
            token_dir = Store(self.hass, STORAGE_VERSION, f"{DOMAIN}_tokens").path
            token_file = Path(f"{token_dir}/{slugify(self._data[CONF_HOST])}.conf")
            if token_file.exists():
                await self.hass.async_add_executor_job(token_file.unlink)
                _LOGGER.info(f"✅ Token invalide supprimé automatiquement : {token_file.name}")
        except Exception as err:
            _LOGGER.debug(f"Impossible de supprimer le token : {err}")

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Étape de liaison avec la Freebox."""
        if user_input is None:
            return self.async_show_form(step_id="link")

        errors = {}
        try:
            fbx = await get_api(self.hass, self._data[CONF_HOST])
            await fbx.open(self._data[CONF_HOST], self._data.get(CONF_PORT, 80))

            await fbx.system.get_config()
            await get_hosts_list_if_supported(fbx)
            await fbx.close()

            # Sauvegarde de la config
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_CONFIG)
            await store.async_save(self._data)

            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
            )

        except AuthorizationError:
            _LOGGER.warning("Token invalide ou autorisation refusée")
            await self._cleanup_invalid_token()
            errors["base"] = "invalid_token"

        except HttpRequestError:
            errors["base"] = "cannot_connect"

        except Exception as err:
            _LOGGER.exception("Erreur inconnue")
            errors["base"] = "unknown"

        return self.async_show_form(step_id="link", errors=errors)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Découverte automatique Zeroconf."""
        host = discovery_info.properties.get("api_domain")
        port = discovery_info.properties.get("https_port")
        if host and port:
            return await self.async_step_user({CONF_HOST: host, CONF_PORT: int(port)})
        return await self.async_step_user()
