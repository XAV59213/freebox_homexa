"""Bundle Programme TNT FR inside Freebox Homexa (MIT, cyclope205)."""
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
CARD_CDN = (
    "https://cdn.jsdelivr.net/gh/cyclope205/programme-tnt-fr@cedaceadd"
    "b0b97bbb2a3e1fe9057ae4594f703d9/custom_components/programme_tnt_fr/www/"
    + CARD_FILENAME
)
_CARD_KEY = "freebox_homexa_tnt_card"
_WS_KEY = "freebox_homexa_tnt_ws"


async def async_setup_bundled_tnt(hass: HomeAssistant) -> ProgrammeTntFrCoordinator | None:
    if hass.config_entries.async_entries(TNT_DOMAIN):
        _LOGGER.info("Programme TNT FR est déjà installé, bundle Homexa ignoré")
        await _async_register_card(hass)
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
    script_url = CARD_CDN
    if card_path.exists():
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL_PATH, str(card_path), cache_headers=False)]
            )
            script_url = CARD_URL_PATH + "?v=2.2.3-homexa"
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Static TNT card path skipped: %s", err)
    add_extra_js_url(hass, script_url)
    hass.data[_CARD_KEY] = True
    await _async_sync_lovelace_resource(hass, script_url)
    _LOGGER.info("Carte programme-tnt-fr-card enregistrée (%s)", script_url)


async def _async_sync_lovelace_resource(hass: HomeAssistant, script_url: str) -> None:
    lovelace_data = hass.data.get("lovelace")
    resources = getattr(lovelace_data, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return
    try:
        if not getattr(resources, "loaded", False):
            await resources.async_load()
        existing = next(
            (
                item
                for item in resources.async_items()
                if "programme-tnt-fr-card.js" in str(item.get("url", ""))
            ),
            None,
        )
        if existing is None:
            await resources.async_create_item({"res_type": "module", "url": script_url})
        elif existing.get("url") != script_url:
            await resources.async_update_item(existing["id"], {"url": script_url})
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Ressource Lovelace TNT non synchronisée", exc_info=True)
