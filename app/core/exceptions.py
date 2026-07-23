"""Application exception hierarchy and HTTP error mapping."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class TicketNotFoundError(ApplicationError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ticket_not_found"
    message = "Ticket not found."


class UserNotFoundError(ApplicationError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "user_not_found"
    message = "User not found."


class TaskDispatchError(ApplicationError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "task_queue_unavailable"
    message = "The ticket was saved, but classification could not be scheduled."


class AuthenticationError(ApplicationError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "authentication_required"
    message = "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"
    message = "Email or password is incorrect."


class AuthorizationError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have permission to perform this action."


class EmailAlreadyExistsError(ApplicationError):
    status_code = status.HTTP_409_CONFLICT
    code = "email_already_registered"
    message = "An account with this email already exists."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        _request: Request, exc: ApplicationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed.",
                    "details": errors,
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(
        request: Request, exc: SQLAlchemyError
    ) -> JSONResponse:
        logger.exception("Database operation failed", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "The database is temporarily unavailable.",
                }
            },
        )
