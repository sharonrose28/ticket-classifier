import json
import logging

from app.core.logging import (
    JsonFormatter,
    bind_request_id,
    bind_ticket_id,
    reset_request_id,
    reset_ticket_id,
)


def test_json_formatter_adds_context_and_extra_fields():
    record = logging.LogRecord(
        "test.logger", logging.INFO, __file__, 10, "classified", (), None
    )
    record.tokens = 50
    record.queue = "engineering"
    request_token = bind_request_id("request-1")
    ticket_token = bind_ticket_id("ticket-1")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_ticket_id(ticket_token)
        reset_request_id(request_token)

    assert payload["request_id"] == "request-1"
    assert payload["ticket_id"] == "ticket-1"
    assert payload["tokens"] == 50
    assert payload["queue"] == "engineering"
