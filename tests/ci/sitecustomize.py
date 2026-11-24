"""Bootstrap du job de tests Home Assistant 2026.11.

Python importe ce module avant les plugins pytest. Home Assistant 2026.11
remplace httpx par httpx2 au démarrage ; le plugin de test importe httpx
plus tôt. Il importe aussi _clear_logger_overwrites depuis
homeassistant.components.logger, déplacé vers components.logger.helpers.
"""


def _prepare() -> None:
    try:
        import httpx2
    except ImportError:
        return
    httpx2.alias_httpx()
    try:
        import homeassistant.components.logger as logger
    except ImportError:
        return
    if hasattr(logger, "_clear_logger_overwrites"):
        return
    from homeassistant.components.logger.helpers import _clear_logger_overwrites

    logger._clear_logger_overwrites = _clear_logger_overwrites


_prepare()
