"""JSON logging and correlation context shared by API and workers."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_ticket_id: ContextVar[str | None] = ContextVar("ticket_id", default=None)

_STANDARD_LOG_RECORD_FIELDS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Serialize standard fields, correlation IDs, and ``extra`` data as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or _request_id.get()
        ticket_id = getattr(record, "ticket_id", None) or _ticket_id.get()
        if request_id:
            payload["request_id"] = str(request_id)
        if ticket_id:
            payload["ticket_id"] = str(ticket_id)

        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_FIELDS and key not in payload:
                payload[key] = _json_safe(value)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str = "INFO") -> None:
    """Configure one JSON stream handler for the current process."""

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # Keep framework, database, and task logs in the same JSON stream.
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy.engine", "celery"):
        named_logger = logging.getLogger(logger_name)
        named_logger.handlers.clear()
        named_logger.propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def bind_request_id(value: str | None) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()


def bind_ticket_id(value: str | None) -> Token[str | None]:
    return _ticket_id.set(value)


def reset_ticket_id(token: Token[str | None]) -> None:
    _ticket_id.reset(token)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)
