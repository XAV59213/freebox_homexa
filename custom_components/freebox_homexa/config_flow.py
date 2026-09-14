"""Flux de configuration pour l'intégration Freebox Homexa."""

import logging
from typing import Any

from freebox_api.exceptions import AuthorizationError, HttpRequestError
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.storage import Store

from .const import (
    CONF_CREATE_LAN_DEVICES,
    CONF_CREATE_WIFI_SENSORS,
    CONF_HOME_POLL_INTERVAL,
    CONF_REMOTE_CODE,
    CONF_REMOTE_CODES,
    CONF_TRACK_LAN_CLIENTS,
    DEFAULT_CREATE_LAN_DEVICES,
    DEFAULT_CREATE_WIFI_SENSORS,
    DEFAULT_HOME_POLL_INTERVAL,
    DEFAULT_TRACK_LAN_CLIENTS,
    DOMAIN,
    HOME_POLL_INTERVAL_OPTIONS,
    STORAGE_VERSION,
    option_remote_code,
    remote_code_field,
)
from .router import get_api, get_hosts_list_if_supported, resolve_token_file

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY_CONFIG = f"{DOMAIN}_config"

FREEBOX_ACCOUNTS_URL = "http://mafreebox.freebox.fr/#Fbx.os.app.settings.Accounts"
FREEBOX_API_URL = "http://mafreebox.freebox.fr/api_version"

_PLACEHOLDERS = {
    "accounts_url": FREEBOX_ACCOUNTS_URL,
    "api_url": FREEBOX_API_URL,
}


def _coerce_home_poll_interval(value: Any) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_HOME_POLL_INTERVAL
    if interval in HOME_POLL_INTERVAL_OPTIONS:
        return interval
    return DEFAULT_HOME_POLL_INTERVAL


def _coerce_remote_code(value: Any) -> str:
    return str(value or "").strip()


def _player_label(player: dict[str, Any]) -> str:
    name = player.get("device_name") or player.get("name") or f"Player {player.get('id')}"
    return str(name)


def _lan_options_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_TRACK_LAN_CLIENTS,
                default=defaults.get(CONF_TRACK_LAN_CLIENTS, DEFAULT_TRACK_LAN_CLIENTS),
            ): bool,
            vol.Required(
                CONF_CREATE_WIFI_SENSORS,
                default=defaults.get(
                    CONF_CREATE_WIFI_SENSORS, DEFAULT_CREATE_WIFI_SENSORS
                ),
            ): bool,
            vol.Required(
                CONF_CREATE_LAN_DEVICES,
                default=defaults.get(
                    CONF_CREATE_LAN_DEVICES, DEFAULT_CREATE_LAN_DEVICES
                ),
            ): bool,
            vol.Required(
                CONF_HOME_POLL_INTERVAL,
                default=_coerce_home_poll_interval(
                    defaults.get(CONF_HOME_POLL_INTERVAL, DEFAULT_HOME_POLL_INTERVAL)
                ),
            ): vol.In(HOME_POLL_INTERVAL_OPTIONS),
        }
    )


def _lan_options_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_TRACK_LAN_CLIENTS: user_input[CONF_TRACK_LAN_CLIENTS],
        CONF_CREATE_WIFI_SENSORS: user_input[CONF_CREATE_WIFI_SENSORS],
        CONF_CREATE_LAN_DEVICES: user_input[CONF_CREATE_LAN_DEVICES],
        CONF_HOME_POLL_INTERVAL: _coerce_home_poll_interval(
            user_input.get(CONF_HOME_POLL_INTERVAL, DEFAULT_HOME_POLL_INTERVAL)
        ),
    }


def _remotes_schema(
    defaults: dict[str, Any],
    players: list[dict[str, Any]],
) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_REMOTE_CODE,
            default=_coerce_remote_code(defaults.get(CONF_REMOTE_CODE)),
        ): str,
    }
    codes = defaults.get(CONF_REMOTE_CODES) if isinstance(defaults.get(CONF_REMOTE_CODES), dict) else {}
    for player in players:
        pid = player.get("id")
        if pid is None:
            continue
        key = remote_code_field(pid)
        default = _coerce_remote_code(
            defaults.get(key) or codes.get(str(pid)) or codes.get(pid)
        )
        fields[vol.Optional(key, default=default)] = str
    return vol.Schema(fields)


def _remotes_from_input(
    user_input: dict[str, Any], players: list[dict[str, Any]]
) -> dict[str, Any]:
    shared = _coerce_remote_code(user_input.get(CONF_REMOTE_CODE))
    per_player: dict[str, str] = {}
    for player in players:
        pid = player.get("id")
        if pid is None:
            continue
        code = _coerce_remote_code(user_input.get(remote_code_field(pid)))
        if code:
            per_player[str(pid)] = code
    result: dict[str, Any] = {CONF_REMOTE_CODE: shared, CONF_REMOTE_CODES: per_player}
    for pid, code in per_player.items():
        result[remote_code_field(pid)] = code
    return result


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour l'intégration Freebox."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._players: list[dict[str, Any]] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FreeboxOptionsFlowHandler()

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

        self._data = {
            CONF_HOST: (user_input or {}).get(CONF_HOST),
            CONF_PORT: (user_input or {}).get(CONF_PORT, 80),
        }
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

    async def _list_players(self) -> list[dict[str, Any]]:
        fbx = await get_api(self.hass, self._data[CONF_HOST])
        try:
            await fbx.open(self._data[CONF_HOST], self._data.get(CONF_PORT, 80))
            players = await fbx.player.get_players() or []
            await fbx.close()
            return list(players)
        except Exception as err:
            _LOGGER.debug("Liste Player indisponible au setup : %s", err)
            try:
                await fbx.close()
            except Exception:
                pass
            return []

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
            try:
                self._players = await fbx.player.get_players() or []
            except Exception:
                self._players = []
            await fbx.close()

            store = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_CONFIG)
            await store.async_save(self._data)

            if self.source == SOURCE_REAUTH:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data=self._data,
                )

            return await self.async_step_lan_options()

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

    async def async_step_lan_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choix LAN + poll Home avant création des devices."""
        if user_input is None:
            return self.async_show_form(
                step_id="lan_options",
                data_schema=_lan_options_schema(),
            )

        self._options = _lan_options_from_input(user_input)
        return await self.async_step_remotes()

    async def async_step_remotes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Codes télécommande réseau des Players."""
        players = self._players or []
        if user_input is None:
            names = ", ".join(_player_label(p) for p in players) or "aucun Player détecté"
            return self.async_show_form(
                step_id="remotes",
                data_schema=_remotes_schema({}, players),
                description_placeholders={"players": names},
            )

        remote_opts = _remotes_from_input(user_input, players)
        self._options.update(remote_opts)
        if remote_opts.get(CONF_REMOTE_CODE):
            self._data[CONF_REMOTE_CODE] = remote_opts[CONF_REMOTE_CODE]
        return self.async_create_entry(
            title=self._data[CONF_HOST],
            data=self._data,
            options=self._options,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        host = discovery_info.properties.get("api_domain") or discovery_info.host
        port = discovery_info.properties.get("https_port") or 80
        return await self.async_step_user({CONF_HOST: host, CONF_PORT: int(port)})


class FreeboxOptionsFlowHandler(OptionsFlow):
    """Options : LAN, intervalle Home, puis télécommandes."""

    def __init__(self) -> None:
        self._pending: dict[str, Any] = {}
        self._players: list[dict[str, Any]] = []

    async def _list_players(self) -> list[dict[str, Any]]:
        router = self.hass.data.get(DOMAIN, {}).get(self.config_entry.unique_id)
        if router is None:
            return []
        try:
            return list(await router._api.player.get_players() or [])
        except Exception as err:
            _LOGGER.debug("Liste Player indisponible dans les options : %s", err)
            return []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._pending = _lan_options_from_input(user_input)
            return await self.async_step_remotes()

        return self.async_show_form(
            step_id="init",
            data_schema=_lan_options_schema(dict(self.config_entry.options)),
        )

    async def async_step_remotes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._players:
            self._players = await self._list_players()
        players = self._players
        defaults = dict(self.config_entry.options)
        if not _coerce_remote_code(defaults.get(CONF_REMOTE_CODE)):
            defaults[CONF_REMOTE_CODE] = self.config_entry.data.get(CONF_REMOTE_CODE) or ""

        if user_input is not None:
            options = {**self._pending, **_remotes_from_input(user_input, players)}
            new_data = dict(self.config_entry.data)
            shared = options.get(CONF_REMOTE_CODE)
            if shared:
                new_data[CONF_REMOTE_CODE] = shared
            else:
                new_data.pop(CONF_REMOTE_CODE, None)
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            return self.async_create_entry(title="", data=options)

        names = ", ".join(_player_label(p) for p in players) or "aucun Player détecté"
        return self.async_show_form(
            step_id="remotes",
            data_schema=_remotes_schema(defaults, players),
            description_placeholders={"players": names},
        )
