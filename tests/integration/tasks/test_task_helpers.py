import uuid
from unittest.mock import AsyncMock

import pytest

from app.tasks import classification
from app.tasks.dead_letter import dead_letter_ticket_task


class ContextSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


@pytest.mark.asyncio
async def test_run_helper_success(monkeypatch):
    process = AsyncMock()
    dispose = AsyncMock()
    monkeypatch.setattr(classification, "get_session_factory", lambda: ContextSession)
    monkeypatch.setattr(
        classification,
        "ClassificationService",
        lambda _session: type("Service", (), {"process": process})(),
    )
    monkeypatch.setattr(classification, "dispose_engine", dispose)

    result = await classification._run_and_record_failure(
        uuid.uuid4(), retry_available=True, task_id="task", retry_count=0
    )

    assert result is None
    process.assert_awaited_once()
    dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_helper_records_retryable_failure(monkeypatch):
    process = AsyncMock(side_effect=TimeoutError("slow"))
    record_failure = AsyncMock()
    services = iter(
        [
            type("Service", (), {"process": process})(),
            type("Service", (), {"record_failure": record_failure})(),
        ]
    )
    monkeypatch.setattr(classification, "get_session_factory", lambda: ContextSession)
    monkeypatch.setattr(classification, "ClassificationService", lambda _session: next(services))
    monkeypatch.setattr(classification, "dispose_engine", AsyncMock())
    ticket_id = uuid.uuid4()

    result = await classification._run_and_record_failure(
        ticket_id, retry_available=True, task_id="task", retry_count=2
    )

    assert result is not None and result.retryable is True
    assert record_failure.await_args.kwargs["will_retry"] is True
    assert record_failure.await_args.kwargs["retry_count"] == 2


def test_dead_letter_task_returns_safe_metadata():
    result = dead_letter_ticket_task.run(
        ticket_id=str(uuid.uuid4()),
        task_id="source-task",
        request_id=None,
        error_type="TimeoutError",
        retry_count=5,
    )
    assert result["task_id"] == "source-task"
    assert result["retry_count"] == 5
