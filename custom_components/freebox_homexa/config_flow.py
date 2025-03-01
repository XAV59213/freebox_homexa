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

from .const import DOMAIN
from .router import get_api, get_hosts_list_if_supported

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_config"

# SECTION: Classe de gestion du flux de configuration
class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour l'intégration Freebox.

    Hérite de ConfigFlow pour fournir les étapes nécessaires à la configuration de la Freebox.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialise le flux de configuration.

        Prépare les données et le stockage pour la configuration.
        """
        self._data: dict[str, Any] = {}
        self._store = None

    # SECTION: Étape utilisateur
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Gère l'étape initiée par l'utilisateur.

        Affiche un formulaire pour entrer l'hôte et le port ou restaure une configuration existante.

        Args:
            user_input: Données fournies par l'utilisateur, si disponibles.

        Returns:
            ConfigFlowResult: Résultat de l'étape de configuration.
        """
        self._store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY)

        if user_input is None:
            # Charger les anciennes données si elles existent
            stored_data = await self._store.async_load()
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

        # Vérifie si la configuration existe déjà
        await self.async_set_unique_id(self._data[CONF_HOST])
        self._abort_if_unique_id_configured()

        return await self.async_step_link()

    # SECTION: Étape de liaison
    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Tente de lier Home Assistant à la Freebox.

        Demande à l'utilisateur d'appuyer sur le bouton de la Freebox pour autoriser la connexion.

        Args:
            user_input: Confirmation de l'utilisateur, si disponible.

        Returns:
            ConfigFlowResult: Résultat de l'étape de liaison.
        """
        if user_input is None:
            return self.async_show_form(step_id="link")

        errors = {}

        try:
            fbx = await get_api(self.hass, self._data[CONF_HOST])

            # Ouvre la connexion et vérifie l'authentification
            await fbx.open(self._data[CONF_HOST], self._data[CONF_PORT])

            # Vérifie les permissions
            await fbx.system.get_config()
            await get_hosts_list_if_supported(fbx)

            # Ferme la connexion
            await fbx.close()

            # Sauvegarde la configuration
            if self._store:
                _LOGGER.info("Sauvegarde de la configuration Freebox.")
                await self._store.async_save(self._data)

            return self.async_create_entry(
                title=self._data[CONF_HOST],
                data=self._data,
            )

        except AuthorizationError as error:
            _LOGGER.error(f"Erreur d'autorisation pour {self._data[CONF_HOST]}: {error}")
            errors["base"] = "register_failed"

        except HttpRequestError as err:
            _LOGGER.error(f"Erreur de connexion à la Freebox {self._data[CONF_HOST]}: {err}")
            errors["base"] = "cannot_connect"

        except Exception as err:
            _LOGGER.exception(f"Erreur inconnue lors de la connexion à la Freebox {self._data[CONF_HOST]}: {err}")
            errors["base"] = "unknown"

        return self.async_show_form(step_id="link", errors=errors)

    # SECTION: Étape Zeroconf
    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Initialise le flux à partir de la découverte Zeroconf.

        Utilise les informations Zeroconf pour préremplir l'hôte et le port.

        Args:
            discovery_info: Informations de découverte Zeroconf.

        Returns:
            ConfigFlowResult: Redirige vers l'étape utilisateur avec les données préremplies.
        """
        zeroconf_properties = discovery_info.properties
        host = zeroconf_properties["api_domain"]
        port = zeroconf_properties["https_port"]
        _LOGGER.debug(f"Découverte Zeroconf: {host}:{port}")
        return await self.async_step_user({CONF_HOST: host, CONF_PORT: port})
