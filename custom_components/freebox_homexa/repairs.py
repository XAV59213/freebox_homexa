"""Actionable Home permission issue; no issue for transient transport failures."""
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


def home_permission_issue_id(entry_id: str) -> str:
    """Scope ownership without embedding hostnames, tokens or device labels."""
    return f"{entry_id}_home_permissions"


@callback
def async_home_permission_denied(hass: HomeAssistant, entry_id: str) -> None:
    ir.async_create_issue(
        hass, DOMAIN, home_permission_issue_id(entry_id),
        is_fixable=False, is_persistent=True,
        severity=ir.IssueSeverity.WARNING, translation_key="home_permissions",
    )


@callback
def async_clear_home_permission_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Clear only after a successful Home read or permanent entry removal."""
    ir.async_delete_issue(hass, DOMAIN, home_permission_issue_id(entry_id))


# Stable technical scopes only: never hostnames, labels, AP IDs or raw errors.
PERMISSION_SOURCES = (
    "wifi_config", "wifi_bss", "wifi_ap", "wifi_stations", "repeaters",
    "disks", "raids", "system", "connection", "calls", "lan", "players",
)


def permission_issue_id(entry_id: str, source: str) -> str:
    if source not in PERMISSION_SOURCES:
        raise ValueError("Unknown permission source")
    return f"{entry_id}_permissions_{source}"


def is_structured_permission_denial(error: Exception) -> bool:
    from freebox_api.exceptions import HttpRequestError, InsufficientPermissionsError
    from .errors import api_error_code

    return isinstance(error, InsufficientPermissionsError) or (
        isinstance(error, HttpRequestError) and api_error_code(error) == "insufficient_rights"
    )


@callback
def async_source_permission_result(
    hass: HomeAssistant, entry_id: str, source: str, error: Exception | None,
) -> None:
    """Only structured SDK rights denial is actionable; no guessed text match."""
    issue_id = permission_issue_id(entry_id, source)
    if error is None:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    elif is_structured_permission_denial(error):
        ir.async_create_issue(
            hass, DOMAIN, issue_id, is_fixable=False, is_persistent=True,
            severity=ir.IssueSeverity.WARNING, translation_key="source_permissions",
            translation_placeholders={"source": source},
        )


@callback
def async_clear_entry_permission_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Permanent removal only; unload must retain a user's ignore preference."""
    async_clear_home_permission_issue(hass, entry_id)
    for source in PERMISSION_SOURCES:
        ir.async_delete_issue(hass, DOMAIN, permission_issue_id(entry_id, source))
