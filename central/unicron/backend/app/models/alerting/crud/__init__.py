"""
CRUD operations for alerting models.
"""
from .alert_rule_crud import (
    create_alert_rule,
    get_alert_rule,
    get_alert_rules_by_organization,
    get_enabled_alert_rules,
    update_alert_rule,
    delete_alert_rule,
)
from .alert_history_crud import (
    create_alert_history,
    get_alert_history,
    get_alert_history_by_rule,
    get_alert_history_by_organization,
    update_alert_history_status,
)
from .alert_state_crud import (
    upsert_alert_state,
    get_alert_state,
    get_alert_state_by_fingerprint,
    get_active_alerts_by_organization,
    delete_alert_state,
)
from .silence_crud import (
    create_silence,
    get_silence,
    get_active_silences,
    get_silences_by_organization,
    expire_silence,
    delete_silence,
)

__all__ = [
    # AlertRule CRUD
    "create_alert_rule",
    "get_alert_rule",
    "get_alert_rules_by_organization",
    "get_enabled_alert_rules",
    "update_alert_rule",
    "delete_alert_rule",
    # AlertHistory CRUD
    "create_alert_history",
    "get_alert_history",
    "get_alert_history_by_rule",
    "get_alert_history_by_organization",
    "update_alert_history_status",
    # AlertState CRUD
    "upsert_alert_state",
    "get_alert_state",
    "get_alert_state_by_fingerprint",
    "get_active_alerts_by_organization",
    "delete_alert_state",
    # Silence CRUD
    "create_silence",
    "get_silence",
    "get_active_silences",
    "get_silences_by_organization",
    "expire_silence",
    "delete_silence",
]
