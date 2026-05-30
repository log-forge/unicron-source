"""
CRUD operations for notification models.
"""
from .channel_crud import (
    create_channel,
    get_channel,
    get_channels,
    update_channel,
    verify_channel,
    delete_channel,
)
from .channel_preset_crud import (
    create_preset,
    get_preset,
    get_presets,
    update_preset,
    delete_preset,
)
from .notification_group_crud import (
    create_group,
    get_group,
    get_groups,
    update_group,
    delete_group,
)
from .notification_preference_crud import (
    create_preference,
    get_preference,
    update_preference,
    delete_preference,
)
from .notification_log_crud import (
    create_log,
    get_log,
    get_logs_by_alert,
    get_logs_by_status,
    get_pending_retries,
    update_log_status,
)

__all__ = [
    # Channel CRUD
    "create_channel",
    "get_channel",
    "get_channels",
    "update_channel",
    "verify_channel",
    "delete_channel",
    # Preset CRUD
    "create_preset",
    "get_preset",
    "get_presets",
    "update_preset",
    "delete_preset",
    # Group CRUD
    "create_group",
    "get_group",
    "get_groups",
    "update_group",
    "delete_group",
    # Preference CRUD
    "create_preference",
    "get_preference",
    "update_preference",
    "delete_preference",
    # Log CRUD
    "create_log",
    "get_log",
    "get_logs_by_alert",
    "get_logs_by_status",
    "get_pending_retries",
    "update_log_status",
]
