"""Flux de configuration pour l'intégration Freebox dans Home Assistant."""
# DESCRIPTION: Ce fichier gère le processus de configuration pour connecter Home Assistant à une Freebox.
# OBJECTIF: Guider l'utilisateur ou Zeroconf à travers les étapes de configuration et de liaison avec la Freebox.

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

from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY
from .router import get_api, get_hosts_list_if_supported

_LOGGER = logging.getLogger(__name__)


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour l'intégration Freebox."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise le flux de configuration."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Gère l'étape initiée par l'utilisateur."""
        if user_input is None:
            # Charger les anciennes données si elles existent
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)
            stored_data = await store.async_load()
            if stored_data:
                _LOGGER.info("Restauration de la configuration Freebox sauvegardée.")
                user_input = stored_data
            else:
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
        await self.async_set_unique_id(self._data[CONF_HOST])
        self._abort_if_unique_id_configured()
        return await self.async_step_link()

    async def _cleanup_invalid_token(self) -> None:
        """Nettoyage automatique du fichier de token invalide."""
        try:
            freebox_path = Store(self.hass, STORAGE_VERSION, STORAGE_KEY).path
            token_file = Path(f"{freebox_path}/{slugify(self._data[CONF_HOST])}.conf")
            if token_file.exists():
                await self.hass.async_add_executor_job(token_file.unlink)
                _LOGGER.info(f"✅ Fichier token invalide supprimé automatiquement : {token_file}")
        except Exception as err:
            _LOGGER.warning(f"Impossible de supprimer le fichier token : {err}")

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tente de lier Home Assistant à la Freebox."""
        if user_input is None:
            return self.async_show_form(step_id="link")

        errors = {}
        try:
            fbx = await get_api(self.hass, self._data[CONF_HOST])
            await fbx.open(self._data[CONF_HOST], self._data.get(CONF_PORT, 80))
            await fbx.system.get_config()
            await get_hosts_list_if_supported(fbx)
            await fbx.close()

            # Sauvegarde de la configuration
            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)
            await store.async_save(self._data)

            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
            )

        except AuthorizationError as error:
            _LOGGER.warning(
                f"Token invalide ou autorisation refusée pour {self._data[CONF_HOST]}: {error}"
            )
            await self._cleanup_invalid_token()
            errors["base"] = "invalid_token"

        except HttpRequestError as err:
            _LOGGER.error(f"Erreur de connexion à la Freebox {self._data[CONF_HOST]}: {err}")
            errors["base"] = "cannot_connect"

        except Exception as err:
            _LOGGER.exception(f"Erreur inconnue pour {self._data[CONF_HOST]}: {err}")
            errors["base"] = "unknown"

        return self.async_show_form(step_id="link", errors=errors)

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Initialise le flux à partir de la découverte Zeroconf."""
        host = discovery_info.properties.get("api_domain")
        port = discovery_info.properties.get("https_port")
        _LOGGER.debug(f"Découverte Zeroconf: {host}:{port}")
        if host and port:
            return await self.async_step_user({CONF_HOST: host, CONF_PORT: int(port)})
        return await self.async_step_user()
