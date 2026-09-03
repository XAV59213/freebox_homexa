"""Bundle Programme TNT FR inside Freebox Homexa (MIT, cyclope205).

Registers the official card URL/element so
`type: custom:programme-tnt-fr-card` works without a second integration.
Skips itself if programme_tnt_fr is already installed.
"""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .tnt_const import DEFAULT_CHANNELS, DOMAIN as TNT_DOMAIN
from .tnt_coordinator import ProgrammeTntFrCoordinator
from .tnt_ws import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

CARD_FILENAME = "programme-tnt-fr-card.js"
CARD_URL_PATH = f"/programme_tnt_fr/{CARD_FILENAME}"
CARD_VERSION = "2.2.3-homexa"
_CARD_KEY = "freebox_homexa_tnt_card"
_WS_KEY = "freebox_homexa_tnt_ws"


async def async_setup_bundled_tnt(hass: HomeAssistant) -> ProgrammeTntFrCoordinator | None:
    """Start XMLTV coordinator + Lovelace card, or reuse an existing TNT install."""
    if hass.config_entries.async_entries(TNT_DOMAIN):
        _LOGGER.info("Programme TNT FR est déjà installé, bundle Homexa ignoré")
        return None

    await _async_register_card(hass)
    if not hass.data.get(_WS_KEY):
        async_register_websocket_api(hass)
        hass.data[_WS_KEY] = True

    coordinator = ProgrammeTntFrCoordinator(hass, DEFAULT_CHANNELS)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Guide TNT XMLTV indisponible pour le moment : %s", err)

    hass.data.setdefault(TNT_DOMAIN, {})["homexa"] = coordinator
    return coordinator


async def _async_register_card(hass: HomeAssistant) -> None:
    if hass.data.get(_CARD_KEY):
        return
    www_dir = Path(__file__).parent / "www"
    card_path = www_dir / CARD_FILENAME
    if not card_path.exists():
        _LOGGER.error("Carte TNT introuvable : %s", card_path)
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, str(card_path), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL_PATH}?v={CARD_VERSION}")
    hass.data[_CARD_KEY] = True
    await _async_sync_lovelace_resource(hass)
    _LOGGER.info("Carte programme-tnt-fr-card enregistrée par Freebox Homexa")


async def _async_sync_lovelace_resource(hass: HomeAssistant) -> None:
    lovelace_data = hass.data.get("lovelace")
    resources = getattr(lovelace_data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return
    target_url = f"{CARD_URL_PATH}?v={CARD_VERSION}"
    try:
        if not getattr(resources, "loaded", False):
            await resources.async_load()
        existing = next(
            (
                item
                for item in resources.async_items()
                if str(item.get("url", "")).split("?", 1)[0] == CARD_URL_PATH
            ),
            None,
        )
        if existing is None:
            await resources.async_create_item({"res_type": "module", "url": target_url})
        elif existing.get("url") != target_url:
            await resources.async_update_item(existing["id"], {"url": target_url})
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Ressource Lovelace TNT non synchronisée", exc_info=True)
