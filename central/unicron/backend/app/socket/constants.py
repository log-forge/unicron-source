"""Shared constants for the Socket.IO layer."""

GLOBAL_ROOM = "room:global"
CONTAINER_FEED_ROOM = "room:containers:feed"

# Namespaces
INTERNAL_NAMESPACE = "/internal"

# Central event names
HERALD_REGISTER_EVENT_NAME = "herald:registered"
HEALTH_EVENT_NAME = "herald:health"
ALERT_FIRED_EVENT = "alert:fired"
ALERT_STACKED_EVENT = "alert:stacked"
ALERT_STATE_CHANGED_EVENT = "alert:state_changed"

# Logs tail
LOGS_TAIL_START = "logs:tail:start"
LOGS_TAIL_STOP = "logs:tail:stop"
LOGS_TAIL_DATA = "logs:tail:data"
LOGS_TAIL_ERROR = "logs:tail:error"

# Internal namespace events (for service-to-service communication)
CONTAINER_EVENT = "container:event"

# Edge event names
REQUEST_INVENTORY_REFRESH_EVENT_NAME = "inventory:refresh"

# Browser feed events
BROWSER_INITIAL_STATE_EVENT = "containers:initial_state"
BROWSER_CONTAINER_EVENT = "containers:event"
BROWSER_HOST_STATUS_EVENT = "containers:host_status"
BROWSER_INVENTORY_EVENT = "containers:inventory_update"
BROWSER_MONITORING_EVENT = "containers:monitoring_state_changed"
BROWSER_LOG_COLLECTION_EVENT = "containers:log_collection_state_changed"
BROWSER_TELEMETRY_HEALTH_EVENT = "containers:telemetry_health"

# Browser stats events
BROWSER_STATS_SUBSCRIBE = "containers:stats:subscribe"
BROWSER_STATS_UNSUBSCRIBE = "containers:stats:unsubscribe"
BROWSER_STATS_DATA_EVENT = "containers:stats:data"

# Browser logs events
BROWSER_LOGS_START = "containers:logs:start"
BROWSER_LOGS_STOP = "containers:logs:stop"
BROWSER_LOGS_DATA = "containers:logs:data"

# Browser files events
BROWSER_FILES_REQUEST = "containers:files:request"
BROWSER_FILES_RESPONSE = "containers:files:response"

# Browser terminal events
BROWSER_TERMINAL_START = "containers:terminal:start"
BROWSER_TERMINAL_INPUT = "containers:terminal:input"
BROWSER_TERMINAL_RESIZE = "containers:terminal:resize"
BROWSER_TERMINAL_STOP = "containers:terminal:stop"
BROWSER_TERMINAL_DATA = "containers:terminal:data"


def room_for_container_stats(container_key: str) -> str:
    return f"room:containers:stats:{container_key}"


def room_for_container_logs(container_key: str) -> str:
    return f"room:containers:logs:{container_key}"


def room_for_container_log_session(session_id: str) -> str:
    return f"room:containers:log_session:{session_id}"


def room_for_container_files(request_id: str) -> str:
    return f"room:containers:files:{request_id}"


def room_for_container_terminal(session_id: str) -> str:
    return f"room:containers:terminal:{session_id}"


__all__ = [
    "GLOBAL_ROOM",
    "CONTAINER_FEED_ROOM",
    "INTERNAL_NAMESPACE",
    "HERALD_REGISTER_EVENT_NAME",
    "HEALTH_EVENT_NAME",
    "ALERT_FIRED_EVENT",
    "ALERT_STACKED_EVENT",
    "ALERT_STATE_CHANGED_EVENT",
    "REQUEST_INVENTORY_REFRESH_EVENT_NAME",
    "LOGS_TAIL_START",
    "LOGS_TAIL_STOP",
    "LOGS_TAIL_DATA",
    "LOGS_TAIL_ERROR",
    "CONTAINER_EVENT",
    "BROWSER_INITIAL_STATE_EVENT",
    "BROWSER_CONTAINER_EVENT",
    "BROWSER_HOST_STATUS_EVENT",
    "BROWSER_INVENTORY_EVENT",
    "BROWSER_MONITORING_EVENT",
    "BROWSER_LOG_COLLECTION_EVENT",
    "BROWSER_TELEMETRY_HEALTH_EVENT",
    "BROWSER_STATS_SUBSCRIBE",
    "BROWSER_STATS_UNSUBSCRIBE",
    "BROWSER_STATS_DATA_EVENT",
    "BROWSER_LOGS_START",
    "BROWSER_LOGS_STOP",
    "BROWSER_LOGS_DATA",
    "BROWSER_FILES_REQUEST",
    "BROWSER_FILES_RESPONSE",
    "BROWSER_TERMINAL_START",
    "BROWSER_TERMINAL_INPUT",
    "BROWSER_TERMINAL_RESIZE",
    "BROWSER_TERMINAL_STOP",
    "BROWSER_TERMINAL_DATA",
    "room_for_container_stats",
    "room_for_container_logs",
    "room_for_container_log_session",
    "room_for_container_files",
    "room_for_container_terminal",
]
