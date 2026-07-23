"""Dead-letter notification task."""

import logging

from app.core.logging import (
    bind_request_id,
    bind_ticket_id,
    reset_request_id,
    reset_ticket_id,
)
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tickets.dead_letter", ignore_result=False)
def dead_letter_ticket_task(
    *,
    ticket_id: str,
    task_id: str,
    request_id: str | None,
    error_type: str,
    retry_count: int,
) -> dict[str, str | int]:
    """Surface an exhausted task without transferring ticket content."""

    request_token = bind_request_id(request_id or task_id)
    ticket_token = bind_ticket_id(ticket_id)
    try:
        logger.error(
            "Ticket classification moved to dead-letter queue",
            extra={
                "event": "ticket.classification.dead_lettered",
                "source_task_id": task_id,
                "error_type": error_type,
                "retry_count": retry_count,
            },
        )
        return {
            "ticket_id": ticket_id,
            "task_id": task_id,
            "error_type": error_type,
            "retry_count": retry_count,
        }
    finally:
        reset_ticket_id(ticket_token)
        reset_request_id(request_token)
