"""Prometheus metrics shared by API and Celery processes."""

from __future__ import annotations

import os

from prometheus_client import CollectorRegistry, Counter, Histogram, REGISTRY
from prometheus_client import generate_latest, multiprocess

CLASSIFICATION_LATENCY = Histogram(
    "ticket_classification_latency_seconds",
    "End-to-end time spent classifying and routing a ticket.",
    buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
OPENAI_FAILURES = Counter(
    "openai_requests_failed_total",
    "OpenAI request attempts that failed.",
    labelnames=("model", "reason"),
)
CLASSIFICATION_RETRIES = Counter(
    "ticket_classification_retries_total",
    "Retries performed by the classification pipeline.",
    labelnames=("layer", "reason"),
)
OPENAI_FALLBACKS = Counter(
    "openai_fallbacks_total",
    "Times classification switched from the primary to fallback model.",
    labelnames=("primary_model", "fallback_model", "reason"),
)
TICKETS_PROCESSED = Counter(
    "tickets_processed_total",
    "Tickets reaching a terminal classification state.",
    labelnames=("status",),
)
CACHE_REQUESTS = Counter(
    "ticket_cache_requests_total",
    "Ticket cache lookups partitioned by outcome.",
    labelnames=("outcome",),
)
BATCH_SIZE = Histogram(
    "ticket_batch_size",
    "Number of tickets persisted and dispatched in one intake batch.",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500),
)


def metrics_payload() -> bytes:
    """Render this process or a configured multiprocess metrics registry."""

    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest(REGISTRY)


def metric_error_reason(error: Exception) -> str:
    """Return a bounded-cardinality failure label."""

    status_code = getattr(error, "status_code", None)
    return f"http_{status_code}" if status_code is not None else type(error).__name__
