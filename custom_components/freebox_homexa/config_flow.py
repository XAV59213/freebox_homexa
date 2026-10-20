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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
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
    remote_code_field,
)
from .tnt_const import (
    CONF_ANNOUNCE_VOLUME,
    CONF_MEDIA_PLAYER_TARGETS,
    CONF_NOTIFY_TARGET,
    CONF_REMINDER_PROFILES,
    CONF_TTS_ENGINE,
    CONF_TMDB_API_KEY,
    CONF_TNT_CHANNELS,
    CONF_TNT_CHANNELS_BELGIQUE,
    CONF_TNT_CHANNELS_FRANCE,
    FRANCE_CHANNELS,
    RTBF_CHANNELS,
    selected_channels,
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


def _options_schema(
    defaults: dict[str, Any] | None = None,
    players: list[dict[str, Any]] | None = None,
) -> vol.Schema:
    defaults = defaults or {}
    players = players or []
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_TRACK_LAN_CLIENTS,
            default=defaults.get(CONF_TRACK_LAN_CLIENTS, DEFAULT_TRACK_LAN_CLIENTS),
        ): bool,
        vol.Required(
            CONF_CREATE_WIFI_SENSORS,
            default=defaults.get(CONF_CREATE_WIFI_SENSORS, DEFAULT_CREATE_WIFI_SENSORS),
        ): bool,
        vol.Required(
            CONF_CREATE_LAN_DEVICES,
            default=defaults.get(CONF_CREATE_LAN_DEVICES, DEFAULT_CREATE_LAN_DEVICES),
        ): bool,
        vol.Required(
            CONF_HOME_POLL_INTERVAL,
            default=_coerce_home_poll_interval(
                defaults.get(CONF_HOME_POLL_INTERVAL, DEFAULT_HOME_POLL_INTERVAL)
            ),
        ): vol.In(HOME_POLL_INTERVAL_OPTIONS),
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


def _options_from_input(
    user_input: dict[str, Any], players: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    players = players or []
    shared = _coerce_remote_code(user_input.get(CONF_REMOTE_CODE))
    per_player: dict[str, str] = {}
    extra: dict[str, str] = {}
    for player in players:
        pid = player.get("id")
        if pid is None:
            continue
        code = _coerce_remote_code(user_input.get(remote_code_field(pid)))
        if code:
            per_player[str(pid)] = code
            extra[remote_code_field(pid)] = code
    return {
        CONF_TRACK_LAN_CLIENTS: user_input[CONF_TRACK_LAN_CLIENTS],
        CONF_CREATE_WIFI_SENSORS: user_input[CONF_CREATE_WIFI_SENSORS],
        CONF_CREATE_LAN_DEVICES: user_input[CONF_CREATE_LAN_DEVICES],
        CONF_HOME_POLL_INTERVAL: _coerce_home_poll_interval(
            user_input.get(CONF_HOME_POLL_INTERVAL, DEFAULT_HOME_POLL_INTERVAL)
        ),
        CONF_REMOTE_CODE: shared,
        CONF_REMOTE_CODES: per_player,
        **extra,
    }


class FreeboxFlowHandler(ConfigFlow, domain=DOMAIN):
    """Gère le flux de configuration pour l'intégration Freebox."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._options: dict[str, Any] = {}
        self._players: list[dict[str, Any]] = []
        self._profiles: list[dict] | None = None
        self._editing_profile: str | None = None

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
        """LAN, intervalle Home et code télécommande avant création des devices."""
        players = self._players or []
        if user_input is None:
            names = ", ".join(_player_label(p) for p in players) or "aucun Player détecté"
            return self.async_show_form(
                step_id="lan_options",
                data_schema=_options_schema({}, players),
                description_placeholders={"players": names},
            )

        self._options = _options_from_input(user_input, players)
        if self._options.get(CONF_REMOTE_CODE):
            self._data[CONF_REMOTE_CODE] = self._options[CONF_REMOTE_CODE]
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


def _tnt_schema(channels_default: list[str], tmdb_api_key_default: str | None) -> vol.Schema:
    """Formulaire « Guide TNT » (adapted from cyclope205/programme-tnt-fr, MIT)."""
    france_options = [
        selector.SelectOptionDict(value=channel_id, label=name)
        for channel_id, name in FRANCE_CHANNELS.items()
    ]
    belgique_options = [
        selector.SelectOptionDict(value=channel_id, label=name)
        for channel_id, name in RTBF_CHANNELS.items()
    ]
    france_default = [c for c in channels_default if c in FRANCE_CHANNELS]
    belgique_default = [c for c in channels_default if c in RTBF_CHANNELS]
    tmdb_selector = selector.selector({"text": {"type": "password"}})
    fields: dict[Any, Any] = {}
    fields[vol.Optional(CONF_TNT_CHANNELS_FRANCE, default=france_default)] = selector.selector(
        {"select": {"options": france_options, "multiple": True, "mode": "list"}}
    )
    fields[
        vol.Optional(CONF_TNT_CHANNELS_BELGIQUE, default=belgique_default)
    ] = selector.selector(
        {"select": {"options": belgique_options, "multiple": True, "mode": "list"}}
    )
    if tmdb_api_key_default:
        fields[vol.Optional(CONF_TMDB_API_KEY, default=tmdb_api_key_default)] = tmdb_selector
    else:
        fields[vol.Optional(CONF_TMDB_API_KEY)] = tmdb_selector
    return vol.Schema(fields)


# --- Profils de rappel : adapted from cyclope205/programme-tnt-fr v3.0.8 (MIT) ---

def _notify_options(hass: HomeAssistant) -> list[selector.SelectOptionDict]:
    """Notify services actually registered on this HA instance.

    Built dynamically (not a hardcoded list) since available targets
    (mobile_app_*, alexa_media_*, ...) differ per install. Excluded:
    "send_message" (needs an entity-based notify target, which this
    install's notify integrations - legacy service-per-device style -
    do not register); "notify" and "persistent_notification" (generic,
    not tied to a specific person's device).

    "alexa_media_*" slugs are kept: the reminder-firing code calls them
    with data={"type": "tts"} so Alexa speaks the message itself, in its
    own voice, with no audio file to fetch. That matters because the
    other option (media_player_targets + tts_engine, using tts.speak)
    needs Amazon's servers to download a generated audio file from this
    HA instance's external URL - which fails for any install that isn't
    reachable from the public internet (e.g. Tailscale-only external_url,
    no Nabu Casa Cloud), producing a "can't access..." error spoken by
    the Echo instead of the reminder.
    """
    services = hass.services.async_services().get("notify", {})
    return [
        selector.SelectOptionDict(value=slug, label=slug)
        for slug in sorted(services)
        if slug not in {"send_message", "notify", "persistent_notification"}
    ]


def _notify_media_player_conflict(
    hass: HomeAssistant,
    notify_targets: list[str],
    media_player_targets: list[str],
) -> bool:
    """True if a notify target and a media_player target hit the same device.

    Alexa Media Player registers both a media_player entity and a
    notify.alexa_media_<slug> service for the same physical Echo. Selecting
    both for one profile double-announces every reminder on that device (see
    _alexa_notify_slug / _async_notify in reminders.py) - block that here
    instead of letting it fail silently at reminder-fire time.
    """
    if not notify_targets or not media_player_targets:
        return False
    notify_slugs = {
        slug[len("notify.") :] if slug.startswith("notify.") else slug
        for slug in notify_targets
    }
    registry = er.async_get(hass)
    for entity_id in media_player_targets:
        entry = registry.async_get(entity_id)
        if entry is None or entry.platform != "alexa_media":
            continue
        slug = "alexa_media_" + entity_id.split(".", 1)[1]
        if slug in notify_slugs:
            return True
    return False


def _profile_schema(
    hass: HomeAssistant,
    name_default: str | None = None,
    notify_default: list[str] | None = None,
    media_player_default: list[str] | None = None,
    tts_default: str | None = None,
    announce_volume_default: float | None = None,
) -> vol.Schema:
    """Form to create or edit one named reminder profile (a person -> their devices).

    Mirrors the notify/media_player/tts fields of the general settings
    form, but scoped to a single named profile instead of the whole
    integration - so two people who each want reminders on their own
    phone/speaker don't have to share one global target list. Passing
    the *_default arguments pre-fills the form for editing an existing
    profile instead of creating a new one.
    """
    notify_selector = selector.selector(
        {
            "select": {
                "options": _notify_options(hass),
                "multiple": True,
                "mode": "dropdown",
            }
        }
    )
    media_player_selector = selector.selector(
        {"entity": {"domain": "media_player", "multiple": True}}
    )
    tts_selector = selector.selector({"entity": {"domain": "tts", "multiple": False}})
    volume_selector = selector.selector(
        {"number": {"min": 0, "max": 1, "step": 0.05, "mode": "slider"}}
    )
    fields: dict = {}
    if name_default is not None:
        fields[vol.Required("name", default=name_default)] = selector.selector({"text": {}})
    else:
        fields[vol.Required("name")] = selector.selector({"text": {}})
    if notify_default:
        fields[vol.Optional(CONF_NOTIFY_TARGET, default=notify_default)] = notify_selector
    else:
        fields[vol.Optional(CONF_NOTIFY_TARGET)] = notify_selector
    if media_player_default:
        fields[
            vol.Optional(CONF_MEDIA_PLAYER_TARGETS, default=media_player_default)
        ] = media_player_selector
    else:
        fields[vol.Optional(CONF_MEDIA_PLAYER_TARGETS)] = media_player_selector
    if tts_default:
        fields[vol.Optional(CONF_TTS_ENGINE, default=tts_default)] = tts_selector
    else:
        fields[vol.Optional(CONF_TTS_ENGINE)] = tts_selector
    if announce_volume_default is not None:
        fields[vol.Optional(CONF_ANNOUNCE_VOLUME, default=announce_volume_default)] = volume_selector
    else:
        fields[vol.Optional(CONF_ANNOUNCE_VOLUME)] = volume_selector
    return vol.Schema(fields)


class FreeboxOptionsFlowHandler(OptionsFlow):
    """Options : LAN, intervalle Home et télécommandes Player sur le même écran."""

    def __init__(self) -> None:
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
        return self.async_show_menu(step_id="init", menu_options=["general", "tnt", "profiles"])

    async def async_step_tnt(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = dict(self.config_entry.options)
        if user_input is not None:
            channels = list(user_input.get(CONF_TNT_CHANNELS_FRANCE) or []) + list(
                user_input.get(CONF_TNT_CHANNELS_BELGIQUE) or []
            )
            if not channels:
                errors["base"] = "no_channels"
            else:
                current[CONF_TNT_CHANNELS] = channels
                current[CONF_TMDB_API_KEY] = (user_input.get(CONF_TMDB_API_KEY) or "").strip()
                return self.async_create_entry(title="", data=current)
        return self.async_show_form(
            step_id="tnt",
            data_schema=_tnt_schema(
                selected_channels(current), current.get(CONF_TMDB_API_KEY) or None
            ),
            errors=errors,
        )

    async def async_step_profiles(self, user_input: dict | None = None):
        if self._profiles is None:
            self._profiles = [
                dict(p) for p in self.config_entry.options.get(CONF_REMINDER_PROFILES, [])
            ]
        actions = [
            selector.SelectOptionDict(value="add", label="Ajouter un profil"),
        ]
        for profile in self._profiles:
            actions.append(
                selector.SelectOptionDict(
                    value=f"edit:{profile['name']}",
                    label=f"Modifier {profile['name']}",
                )
            )
            actions.append(
                selector.SelectOptionDict(
                    value=f"remove:{profile['name']}",
                    label=f"Supprimer {profile['name']}",
                )
            )
        actions.append(selector.SelectOptionDict(value="done", label="Terminer"))

        if user_input is not None:
            action = user_input.get("action")
            if action == "add":
                self._editing_profile = None
                return await self.async_step_add_profile()
            if action and action.startswith("edit:"):
                self._editing_profile = action[len("edit:") :]
                return await self.async_step_add_profile()
            if action and action.startswith("remove:"):
                name = action[len("remove:") :]
                self._profiles = [p for p in self._profiles if p["name"] != name]
                return await self.async_step_profiles()
            return self._save_profiles()

        names = ", ".join(p["name"] for p in self._profiles) or "aucun profil configuré"
        return self.async_show_form(
            step_id="profiles",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="done"): selector.selector(
                        {"select": {"options": actions, "mode": "list"}}
                    )
                }
            ),
            description_placeholders={"profiles": names},
        )

    async def async_step_add_profile(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        editing_name = self._editing_profile
        if user_input is not None:
            name = (user_input.get("name") or "").strip()
            if not name:
                errors["base"] = "no_name"
            elif any(
                p["name"] == name
                for p in self._profiles
                if editing_name is None or p["name"] != editing_name
            ):
                errors["base"] = "duplicate_name"
            elif _notify_media_player_conflict(
                self.hass,
                user_input.get(CONF_NOTIFY_TARGET) or [],
                user_input.get(CONF_MEDIA_PLAYER_TARGETS) or [],
            ):
                errors["base"] = "device_conflict"
            else:
                profile: dict = {"name": name}
                if user_input.get(CONF_NOTIFY_TARGET):
                    profile[CONF_NOTIFY_TARGET] = user_input[CONF_NOTIFY_TARGET]
                if user_input.get(CONF_MEDIA_PLAYER_TARGETS):
                    profile[CONF_MEDIA_PLAYER_TARGETS] = user_input[CONF_MEDIA_PLAYER_TARGETS]
                if user_input.get(CONF_TTS_ENGINE):
                    profile[CONF_TTS_ENGINE] = user_input[CONF_TTS_ENGINE]
                if user_input.get(CONF_ANNOUNCE_VOLUME) is not None:
                    profile[CONF_ANNOUNCE_VOLUME] = user_input[CONF_ANNOUNCE_VOLUME]
                if editing_name is not None:
                    self._profiles = [
                        profile if p["name"] == editing_name else p
                        for p in self._profiles
                    ]
                else:
                    self._profiles.append(profile)
                self._editing_profile = None
                return await self.async_step_profiles()

        existing = None
        if editing_name is not None:
            existing = next(
                (p for p in self._profiles if p["name"] == editing_name), None
            )

        if errors and user_input is not None:
            name_default = user_input.get("name")
            notify_default = user_input.get(CONF_NOTIFY_TARGET)
            media_player_default = user_input.get(CONF_MEDIA_PLAYER_TARGETS)
            tts_default = user_input.get(CONF_TTS_ENGINE)
            announce_volume_default = user_input.get(CONF_ANNOUNCE_VOLUME)
        else:
            name_default = existing["name"] if existing else None
            notify_default = existing.get(CONF_NOTIFY_TARGET) if existing else None
            media_player_default = (
                existing.get(CONF_MEDIA_PLAYER_TARGETS) if existing else None
            )
            tts_default = existing.get(CONF_TTS_ENGINE) if existing else None
            announce_volume_default = (
                existing.get(CONF_ANNOUNCE_VOLUME) if existing else None
            )

        return self.async_show_form(
            step_id="add_profile",
            data_schema=_profile_schema(
                self.hass,
                name_default=name_default,
                notify_default=notify_default,
                media_player_default=media_player_default,
                tts_default=tts_default,
                announce_volume_default=announce_volume_default,
            ),
            errors=errors,
        )

    def _save_profiles(self) -> ConfigFlowResult:
        data = dict(self.config_entry.options)
        data[CONF_REMINDER_PROFILES] = self._profiles or []
        return self.async_create_entry(title="", data=data)

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._players:
            self._players = await self._list_players()
        players = self._players
        defaults = dict(self.config_entry.options)
        if not _coerce_remote_code(defaults.get(CONF_REMOTE_CODE)):
            defaults[CONF_REMOTE_CODE] = self.config_entry.data.get(CONF_REMOTE_CODE) or ""

        if user_input is not None:
            options = _options_from_input(user_input, players)
            new_data = dict(self.config_entry.data)
            shared = options.get(CONF_REMOTE_CODE)
            if shared:
                new_data[CONF_REMOTE_CODE] = shared
            else:
                new_data.pop(CONF_REMOTE_CODE, None)
            self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
            # Conserver les options des autres écrans (Guide TNT, rappels…)
            merged = {
                key: value
                for key, value in self.config_entry.options.items()
                if not key.startswith(f"{CONF_REMOTE_CODE}_")
            }
            merged.update(options)
            return self.async_create_entry(title="", data=merged)

        names = ", ".join(_player_label(p) for p in players) or "aucun Player détecté"
        return self.async_show_form(
            step_id="general",
            data_schema=_options_schema(defaults, players),
            description_placeholders={"players": names},
        )
