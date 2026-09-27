"""Register the Lovelace Homexa card with Home Assistant."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from aiohttp import web

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from ..const import CARD_FILENAME, LOCAL_CARD_PATH, STATIC_CARD_PATH, URL_BASE, VERSION

_LOGGER = logging.getLogger(__name__)

_MAX_RESOURCE_RETRIES = 12
_RETRY_SECONDS = 5


def _lovelace_data(hass: HomeAssistant) -> Any:
    return hass.data.get("lovelace")


def _resources(lovelace: Any) -> Any:
    if lovelace is None:
        return None
    if isinstance(lovelace, dict):
        return lovelace.get("resources")
    return getattr(lovelace, "resources", None)


def _path_only(url: str) -> str:
    return str(url).split("?", 1)[0]


def _copy_card_to_www(hass: HomeAssistant) -> Path | None:
    try:
        src = Path(__file__).parent / CARD_FILENAME
        dest = Path(hass.config.path("www")) / CARD_FILENAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return dest
    except OSError:
        _LOGGER.warning("Impossible de copier la carte Lovelace dans www")
        return None


class HomexaCardView(HomeAssistantView):
    """Always serve the card JS from the integration package."""

    url = STATIC_CARD_PATH
    name = "api:freebox_homexa:card"
    requires_auth = False

    async def get(self, request):
        path = Path(__file__).parent / CARD_FILENAME
        body = await request.app["hass"].async_add_executor_job(path.read_text, "utf-8")
        return web.Response(
            text=body,
            content_type="text/javascript",
            headers={"Cache-Control": "no-cache"},
        )


class JSModuleRegistration:
    """Serve and register the Freebox Homexa Lovelace card."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._retries = 0
        self._started_listen = False

    async def async_register(self) -> None:
        await self._async_register_path()
        try:
            self.hass.http.register_view(HomexaCardView())
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Vue HTTP de la carte déjà enregistrée")

        await self.hass.async_add_executor_job(_copy_card_to_www, self.hass)
        add_extra_js_url(self.hass, f"{STATIC_CARD_PATH}?v={VERSION}")
        add_extra_js_url(self.hass, f"{LOCAL_CARD_PATH}?v={VERSION}")

        if self.hass.is_running:
            await self._async_register_lovelace_resources()
        elif not self._started_listen:
            self._started_listen = True

            @callback
            def _schedule_started(_event: Event) -> None:
                self.hass.async_create_task(self._async_register_lovelace_resources())

            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _schedule_started)

    async def _async_register_path(self) -> None:
        try:
            await self.hass.http.async_register_static_paths(
                [StaticPathConfig(URL_BASE, Path(__file__).parent, False)]
            )
        except RuntimeError:
            _LOGGER.debug("Chemin statique déjà enregistré : %s", URL_BASE)

    async def _async_register_lovelace_resources(self) -> None:
        resources = _resources(_lovelace_data(self.hass))
        if resources is None:
            self._schedule_retry("ressources Lovelace indisponibles")
            return

        load = getattr(resources, "async_load", None)
        if callable(load) and not getattr(resources, "loaded", False):
            try:
                await load()
            except Exception:  # noqa: BLE001
                self._schedule_retry("async_load failed")
                return

        try:
            items = list(resources.async_items())
        except Exception:  # noqa: BLE001
            self._schedule_retry("async_items failed")
            return

        try:
            await self._async_sync_modules(resources, items)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Échec d'enregistrement de la carte Lovelace")
            self._schedule_retry("create/update failed")

    def _schedule_retry(self, reason: str) -> None:
        if self._retries >= _MAX_RESOURCE_RETRIES:
            _LOGGER.warning(
                "Carte Lovelace non enregistrée après %s essais (%s). "
                "Ajoute %s en module JavaScript : Paramètres → Tableaux de bord → Ressources",
                _MAX_RESOURCE_RETRIES,
                reason,
                f"{STATIC_CARD_PATH}?v={VERSION}",
            )
            return
        self._retries += 1
        async_call_later(self.hass, _RETRY_SECONDS, self._retry_resources)

    async def _retry_resources(self, _now: Any) -> None:
        await self._async_register_lovelace_resources()

    async def _async_sync_modules(self, resources: Any, items: list[dict]) -> None:
        wanted = {STATIC_CARD_PATH, LOCAL_CARD_PATH}
        versioned_static = f"{STATIC_CARD_PATH}?v={VERSION}"
        matching = [item for item in items if _path_only(item.get("url", "")) in wanted]

        if matching:
            for resource in matching:
                path = _path_only(resource.get("url", ""))
                versioned = f"{path}?v={VERSION}"
                if resource.get("url") != versioned:
                    await resources.async_update_item(
                        resource["id"],
                        {"res_type": "module", "url": versioned},
                    )
            return

        await resources.async_create_item({"res_type": "module", "url": versioned_static})
        _LOGGER.info("Carte Lovelace Homexa enregistrée : %s", versioned_static)
