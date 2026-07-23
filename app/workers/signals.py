"""Celery worker lifecycle hooks for Prometheus multiprocess cleanup."""

import os

from celery.signals import worker_process_shutdown
from prometheus_client import multiprocess


@worker_process_shutdown.connect
def cleanup_prometheus_process_file(pid: int | None = None, **_kwargs) -> None:
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        multiprocess.mark_process_dead(pid or os.getpid())
