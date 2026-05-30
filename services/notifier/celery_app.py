"""Celery application configuration for notification tasks.

Configures:
- Gevent-friendly queues/concurrency defaults (pool selected at runtime via `-P gevent`)
- Two-level priority queues (high for critical/error, normal for warning/info)
- Task serialization and retry settings
"""

from celery import Celery
from kombu import Exchange, Queue

from app.core.config import settings
from app.core.encryption import init_encryption

# Workers must share the same Fernet key as the API process so they can
# decrypt stored channel credentials before dispatch.
init_encryption()

celery_app = Celery(
    "notifier",
    broker=settings.celery_broker,
    backend=settings.celery_broker,  # Use Redis as result backend
    include=["app.tasks.notification_tasks"],
)

# Define exchanges
default_exchange = Exchange("default", type="direct")
priority_exchange = Exchange("priority", type="direct")

# Define queues with priorities
# High priority: critical and error severity alerts
# Normal priority: warning and info alerts
celery_app.conf.task_queues = (
    Queue(
        "high",
        priority_exchange,
        routing_key="high",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "normal",
        priority_exchange,
        routing_key="normal",
        queue_arguments={"x-max-priority": 5},
    ),
)

# Default queue for tasks without explicit routing
celery_app.conf.task_default_queue = "normal"
celery_app.conf.task_default_exchange = "priority"
celery_app.conf.task_default_routing_key = "normal"

# Task routing based on severity
celery_app.conf.task_routes = {
    "app.tasks.notification_tasks.send_notification_high": {
        "queue": "high",
        "routing_key": "high",
    },
    "app.tasks.notification_tasks.send_notification": {
        "queue": "normal",
        "routing_key": "normal",
    },
}

# Celery configuration
celery_app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Reliability settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Retry if worker dies
    # Concurrency defaults (runtime command selects pool strategy)
    worker_prefetch_multiplier=4,  # Prefetch tasks for efficiency
    worker_concurrency=50,  # Default 50 greenlets per worker
    # Result expiration
    result_expires=3600,  # Results expire after 1 hour
    # Task time limits
    task_soft_time_limit=45,  # Soft limit: 45 seconds
    task_time_limit=60,  # Hard limit: 60 seconds
    # Broker connection retry
    broker_connection_retry_on_startup=True,
)
