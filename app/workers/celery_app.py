"""Celery application and production worker configuration."""

from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

celery_app = Celery(
    "ticket_classifier",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.classification", "app.tasks.dead_letter"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_concurrency=settings.celery_worker_concurrency,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_hijack_root_logger=False,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    result_backend_transport_options={
        "visibility_timeout": 3600,
        "global_keyprefix": "ticket-classifier_",
        "retry_policy": {"timeout": 5.0},
    },
    visibility_timeout=3600,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 2,
    },
    result_extended=True,
    result_expires=3600,
    task_default_exchange="ticket_classifier",
    task_default_exchange_type="direct",
    task_default_routing_key="classification.default",
    task_queues=(
        Queue(
            "classification.default",
            Exchange("ticket_classifier", type="direct"),
            routing_key="classification.default",
        ),
        Queue(
            "classification.dead_letter",
            Exchange("ticket_classifier", type="direct"),
            routing_key="classification.dead_letter",
        ),
    ),
    task_routes={
        "tickets.classify": {"queue": "classification.default"},
        "tickets.dead_letter": {"queue": "classification.dead_letter"},
    },
)

# Register lifecycle signal handlers after the Celery app is configured.
from app.workers import signals as _signals  # noqa: E402,F401
