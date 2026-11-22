"""Messagerie vocale pour la carte Téléphone, par WebSocket.

Même principe que le journal d'appels : la liste d'état n'a pas de numéro.
La carte ne reçoit le numéro que si elle le demande (``include_number``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.const import ERR_INVALID_FORMAT, ERR_NOT_FOUND
from homeassistant.components.websocket_api.decorators import websocket_command
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .voicemail import (
    async_delete_voicemail,
    async_mark_voicemail_read,
    messages_of,
    public_message,
    unread_count,
)
from .voicemail_audio import signed_voicemail_path

if TYPE_CHECKING:
    from .router import FreeboxConfigEntry, FreeboxRouter

_ACTIONS = frozenset({"list", "mark_read", "delete", "audio_url"})
_READ_ACTIONS = frozenset({"list", "audio_url"})


def _loaded_entries(hass: HomeAssistant) -> list[FreeboxConfigEntry]:
    return [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]


def _router(entry: FreeboxConfigEntry) -> FreeboxRouter:
    return entry.runtime_data


@websocket_command(
    {
        "type": "freebox_homexa/voicemails",
        vol.Optional("action"): str,
        vol.Optional("config_entry_id"): str,
        vol.Optional("entity_id"): str,
        vol.Optional("message_id"): str,
        vol.Optional("include_number"): bool,
        vol.Optional("codec"): str,
    }
)
@websocket_api.async_response
async def websocket_homexa_voicemails(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, object]
) -> None:
    """Liste, marque lu, supprime, ou signe une URL audio."""
    message_id = msg["id"]
    action = msg.get("action", "list")
    if not isinstance(action, str) or action not in _ACTIONS:
        raise vol.Invalid("Invalid voicemail action", path=["action"])
    codec = msg.get("codec", "wav")
    if not isinstance(codec, str) or codec not in ("wav", "mp3"):
        raise vol.Invalid("Invalid audio codec", path=["codec"])
    include_number = msg.get("include_number", False)
    if not isinstance(include_number, bool):
        include_number = False
    entity_id = msg.get("entity_id")
    config_entry_id = msg.get("config_entry_id")
    voicemail_id = msg.get("message_id")
    if action != "list" and not isinstance(voicemail_id, str):
        raise vol.Invalid("Invalid voicemail id", path=["message_id"])

    entry = _resolve_entry(hass, connection, message_id, entity_id, config_entry_id, action)
    if entry is None:
        return
    router = _router(entry)
    try:
        if action == "mark_read":
            assert isinstance(voicemail_id, str)
            await async_mark_voicemail_read(router, voicemail_id)
        elif action == "delete":
            assert isinstance(voicemail_id, str)
            await async_delete_voicemail(router, voicemail_id)
        elif action == "audio_url":
            assert isinstance(voicemail_id, str)
            url = signed_voicemail_path(
                hass, entry.entry_id, voicemail_id, mp3=codec == "mp3"
            )
            connection.send_result(message_id, {"url": url})
            return
    except ServiceValidationError:
        connection.send_error(message_id, ERR_INVALID_FORMAT, "Identifiant de message vocal invalide")
        return
    except HomeAssistantError:
        connection.send_error(message_id, "home_assistant_error", "Messagerie vocale indisponible")
        return
    except Exception:
        connection.send_error(message_id, "home_assistant_error", "Messagerie vocale indisponible")
        return
    found = messages_of(router)
    connection.send_result(
        message_id,
        {
            "messages": [public_message(item, include_number=include_number) for item in found],
            "unread": unread_count(found),
            "total": len(found),
        },
    )


def _resolve_entry(
    hass: HomeAssistant,
    connection: ActiveConnection,
    message_id: int,
    entity_id: object,
    config_entry_id: object,
    action: str,
) -> FreeboxConfigEntry | None:
    from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ

    entries = _loaded_entries(hass)
    policy = POLICY_READ if action in _READ_ACTIONS else POLICY_CONTROL
    if isinstance(entity_id, str):
        row = er.async_get(hass).async_get(entity_id)
        unique_id = str(row.unique_id or "") if row is not None else ""
        if (
            row is None
            or row.platform != DOMAIN
            or row.domain != "sensor"
            or not unique_id.endswith("Messages vocaux non lus")
        ):
            connection.send_error(message_id, ERR_NOT_FOUND, "Capteur de messagerie Freebox Homexa introuvable")
            return None
        if not connection.user.permissions.check_entity(entity_id, policy):
            raise Unauthorized(entity_id=entity_id)
        entry = next((item for item in entries if item.entry_id == row.config_entry_id), None)
        if entry is None:
            connection.send_error(message_id, ERR_NOT_FOUND, "Aucune Freebox Homexa chargée pour ce capteur")
            return None
        if isinstance(config_entry_id, str) and config_entry_id != entry.entry_id:
            connection.send_error(message_id, ERR_INVALID_FORMAT, "Entrée Freebox incohérente")
            return None
        return entry
    if not connection.user.is_admin:
        raise Unauthorized()
    if isinstance(config_entry_id, str):
        entry = next((item for item in entries if item.entry_id == config_entry_id), None)
        if entry is None:
            connection.send_error(message_id, ERR_NOT_FOUND, "Aucune Freebox Homexa chargée pour ce capteur")
            return None
        return entry
    if len(entries) == 1:
        return entries[0]
    connection.send_error(message_id, ERR_NOT_FOUND, "Aucune Freebox Homexa chargée pour ce capteur")
    return None


def async_register_voicemail_websocket_api(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, websocket_homexa_voicemails)
