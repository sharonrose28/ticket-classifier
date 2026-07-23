import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from celery.exceptions import Retry

from app.core.logging import bind_request_id, reset_request_id
from app.tasks import classification


def test_celery_task_success(monkeypatch):
    async def success(*_args, **_kwargs):
        return None

    monkeypatch.setattr(classification, "_run_and_record_failure", success)
    ticket_id = str(uuid.uuid4())

    result = classification.classify_ticket_task.run(ticket_id, "request-1")
    assert result == {"ticket_id": ticket_id, "status": "complete"}


def test_celery_task_retries_transient_failure(monkeypatch):
    async def failure(*_args, **_kwargs):
        return classification.WorkflowFailure(TimeoutError("temporary"), True)

    monkeypatch.setattr(classification, "_run_and_record_failure", failure)
    retry = Mock(side_effect=Retry("retrying"))
    monkeypatch.setattr(classification.classify_ticket_task, "retry", retry)
    with pytest.raises(Retry):
        classification.classify_ticket_task.run(str(uuid.uuid4()), "request-2")
    assert retry.call_args.kwargs["countdown"] == 10


def test_celery_task_dead_letters_permanent_failure(monkeypatch):
    error = ValueError("invalid output")

    async def failure(*_args, **_kwargs):
        return classification.WorkflowFailure(error, False)

    publish = Mock()
    monkeypatch.setattr(classification, "_run_and_record_failure", failure)
    monkeypatch.setattr(classification.dead_letter_ticket_task, "apply_async", publish)
    ticket_id = str(uuid.uuid4())

    with pytest.raises(ValueError, match="invalid output"):
        classification.classify_ticket_task.run(ticket_id, "request-3")
    assert publish.call_args.kwargs["queue"] == "classification.dead_letter"
    assert publish.call_args.kwargs["kwargs"]["ticket_id"] == ticket_id


def test_dead_letter_publish_failure_does_not_hide_original(monkeypatch, caplog):
    error = ValueError("original")

    async def failure(*_args, **_kwargs):
        return classification.WorkflowFailure(error, False)

    monkeypatch.setattr(classification, "_run_and_record_failure", failure)
    monkeypatch.setattr(
        classification.dead_letter_ticket_task,
        "apply_async",
        Mock(side_effect=ConnectionError("redis unavailable")),
    )

    with pytest.raises(ValueError, match="original"):
        classification.classify_ticket_task.run(str(uuid.uuid4()), "request-4")
    assert "Could not publish dead-letter notification" in caplog.text


def test_enqueue_propagates_request_id(monkeypatch):
    published = SimpleNamespace(id="celery-task-1")
    apply_async = Mock(return_value=published)
    monkeypatch.setattr(classification.classify_ticket_task, "apply_async", apply_async)
    request_token = bind_request_id("request-propagated")
    ticket_id = uuid.uuid4()
    try:
        task_id = classification.enqueue_ticket_classification(ticket_id)
    finally:
        reset_request_id(request_token)

    assert task_id == "celery-task-1"
    assert apply_async.call_args.kwargs["args"] == [
        str(ticket_id),
        "request-propagated",
    ]
