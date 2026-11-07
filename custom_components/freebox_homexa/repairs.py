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
