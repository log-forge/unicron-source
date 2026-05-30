"""
Rule template definitions for common monitoring scenarios.

This service provides 11 predefined rule templates across 4 categories.
"""

from typing import Any, Dict, List, Optional

from app.schemas.template_schemas import TemplateCategory


# Template definitions - ported from LogForge
RULE_TEMPLATES = [
    # STABILITY CATEGORY
    {
        "id": "restart_loop_detection",
        "name": "Restart Loop Detection",
        "description": "Detect when a container restarts too frequently and automatically stop it to prevent resource waste",
        "category": TemplateCategory.STABILITY.value,
        "trigger_type": "container_event",
        "trigger_value": "start",
        "timeline_minutes": 5,
        "timeline_count": 3,
        "trigger_config": {
            "trigger_value": "start",
            "timeline_minutes": 5,
            "timeline_count": 3,
        },
        "actions": [
            {"type": "stop_container", "config": {}, "delay_seconds": None},
            {"type": "notification", "config": {}, "delay_seconds": 30}
        ],
        "customizable_fields": ["timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Stability", "Events", "Stop", "Notify", "Restart"]
    },
    {
        "id": "crash_loop_detection",
        "name": "Crash Loop Detection",
        "description": "Detect when a container crashes repeatedly and kill it to prevent system instability",
        "category": TemplateCategory.STABILITY.value,
        "trigger_type": "container_event",
        "trigger_value": "stop",
        "timeline_minutes": 10,
        "timeline_count": 5,
        "trigger_config": {
            "trigger_value": "stop",
            "timeline_minutes": 10,
            "timeline_count": 5,
        },
        "actions": [
            {"type": "kill_container", "config": {}, "delay_seconds": None},
            {"type": "notification", "config": {}, "delay_seconds": 60}
        ],
        "customizable_fields": ["timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Stability", "Events", "Kill", "Notify", "Crash"]
    },
    {
        "id": "failed_start_detection",
        "name": "Failed Start Detection",
        "description": "Alert when a container fails to start multiple times (requires manual intervention)",
        "category": TemplateCategory.STABILITY.value,
        "trigger_type": "container_event",
        "trigger_value": "start",
        "timeline_minutes": 15,
        "timeline_count": 3,
        "trigger_config": {
            "trigger_value": "start",
            "timeline_minutes": 15,
            "timeline_count": 3,
        },
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None}
        ],
        "customizable_fields": ["timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Stability", "Events", "Notify", "Start"]
    },

    # PERFORMANCE CATEGORY
    {
        "id": "high_cpu_usage",
        "name": "High CPU Usage",
        "description": "Alert and restart container when CPU usage exceeds threshold for sustained period",
        "category": TemplateCategory.PERFORMANCE.value,
        "trigger_type": "metric_threshold",
        "trigger_value": {
            "metric_type": "cpu_percent",
            "threshold": 80.0,
            "operator": ">"
        },
        "timeline_minutes": 5,
        "actions": [
            {"type": "restart_container", "config": {}, "delay_seconds": None},
            {"type": "notification", "config": {}, "delay_seconds": 120}
        ],
        "customizable_fields": ["trigger_value.threshold", "timeline_minutes"],
        "required_metrics": ["cpu_percent"],
        "tags": ["Performance", "Metrics", "Restart", "Notify", "CPU"]
    },
    {
        "id": "high_memory_usage",
        "name": "High Memory Usage",
        "description": "Alert and restart container when memory usage exceeds threshold for sustained period",
        "category": TemplateCategory.PERFORMANCE.value,
        "trigger_type": "metric_threshold",
        "trigger_value": {
            "metric_type": "memory_percent",
            "threshold": 85.0,
            "operator": ">"
        },
        "timeline_minutes": 3,
        "actions": [
            {"type": "restart_container", "config": {}, "delay_seconds": None},
            {"type": "notification", "config": {}, "delay_seconds": 90}
        ],
        "customizable_fields": ["trigger_value.threshold", "timeline_minutes"],
        "required_metrics": ["memory_percent"],
        "tags": ["Performance", "Metrics", "Restart", "Notify", "Memory"]
    },
    {
        "id": "low_disk_space",
        "name": "Low Disk Space",
        "description": "Alert when disk usage is critically high (notification only - requires manual intervention)",
        "category": TemplateCategory.PERFORMANCE.value,
        "trigger_type": "metric_threshold",
        "trigger_value": {
            "metric_type": "disk_usage",
            "threshold": 90.0,
            "operator": ">"
        },
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None}
        ],
        "customizable_fields": ["trigger_value.threshold"],
        "required_metrics": ["disk_usage"],
        "tags": ["Performance", "Metrics", "Notify", "Disk"]
    },

    # LOGS CATEGORY
    {
        "id": "error_flood_detection",
        "name": "Error Flood Detection",
        "description": "Alert when error messages appear too frequently in container logs",
        "category": TemplateCategory.LOGS.value,
        "trigger_type": "keyword",
        "trigger_value": "error",
        "timeline_minutes": 2,
        "timeline_count": 10,
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None}
        ],
        "customizable_fields": ["trigger_value", "timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Logs", "Notify", "Error"]
    },
    {
        "id": "out_of_memory_detection",
        "name": "Out of Memory Detection",
        "description": "Detect OOM errors and automatically restart the container",
        "category": TemplateCategory.LOGS.value,
        "trigger_type": "keyword",
        "trigger_value": "OutOfMemoryError",
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None},
            {"type": "restart_container", "config": {}, "delay_seconds": 30}
        ],
        "customizable_fields": ["trigger_value"],
        "required_metrics": [],
        "tags": ["Logs", "Notify", "Restart", "Memory"]
    },
    {
        "id": "database_connection_issues",
        "name": "Database Connection Issues",
        "description": "Alert when database connectivity problems are detected in logs",
        "category": TemplateCategory.LOGS.value,
        "trigger_type": "keyword",
        "trigger_value": "connection refused",
        "timeline_minutes": 5,
        "timeline_count": 3,
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None}
        ],
        "customizable_fields": ["trigger_value", "timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Logs", "Notify", "Database"]
    },

    # SECURITY CATEGORY
    {
        "id": "unauthorized_access_attempts",
        "name": "Unauthorized Access Attempts",
        "description": "Alert when multiple unauthorized access attempts are detected",
        "category": TemplateCategory.SECURITY.value,
        "trigger_type": "keyword",
        "trigger_value": "unauthorized",
        "timeline_minutes": 10,
        "timeline_count": 5,
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None}
        ],
        "customizable_fields": ["trigger_value", "timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Security", "Logs", "Notify", "Access"]
    },
    {
        "id": "suspicious_network_activity",
        "name": "Suspicious Network Activity",
        "description": "Alert on suspicious network patterns in container logs",
        "category": TemplateCategory.SECURITY.value,
        "trigger_type": "keyword",
        "trigger_value": "suspicious",
        "timeline_minutes": 15,
        "timeline_count": 3,
        "actions": [
            {"type": "notification", "config": {}, "delay_seconds": None}
        ],
        "customizable_fields": ["trigger_value", "timeline_minutes", "timeline_count"],
        "required_metrics": [],
        "tags": ["Security", "Logs", "Notify", "Network"]
    },
]


def get_templates_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all templates organized by category.

    Returns:
        Dictionary mapping category names to lists of template dictionaries.
    """
    templates_by_category: Dict[str, List[Dict[str, Any]]] = {
        category.value: [] for category in TemplateCategory
    }

    for template in RULE_TEMPLATES:
        category = template["category"]
        templates_by_category[category].append(template)

    return templates_by_category


def get_template_by_id(template_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific template by ID.

    Args:
        template_id: The template identifier.

    Returns:
        Template dictionary if found, None otherwise.
    """
    for template in RULE_TEMPLATES:
        if template["id"] == template_id:
            return template
    return None


def get_all_required_metrics() -> List[str]:
    """
    Get all metrics that are required by templates.

    Returns:
        List of unique metric names required by any template.
    """
    required_metrics = set()
    for template in RULE_TEMPLATES:
        required_metrics.update(template.get("required_metrics", []))
    return sorted(list(required_metrics))
