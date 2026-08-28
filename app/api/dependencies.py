"""Shared FastAPI dependency providers."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import session_scope
from app.services.ticket_service import TicketService
from app.services.cache_service import TicketCache
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token
from app.models.user import User, UserRole
from app.repositories.users import UserRepository

SessionDep = Annotated[AsyncSession, Depends(session_scope)]


async def get_current_user(request: Request, session: SessionDep) -> User:
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    payload = decode_access_token(token or "", secret=settings.jwt_secret_key.get_secret_value())
    if payload is None:
        raise AuthenticationError()
    user = await UserRepository(session).get(payload.subject)
    if user is None or not user.is_active:
        raise AuthenticationError()
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    async def dependency(user: CurrentUserDep) -> User:
        if user.role not in roles:
            raise AuthorizationError()
        return user
    return dependency


def get_ticket_service(request: Request, session: SessionDep, user: CurrentUserDep) -> TicketService:
    """Construct a request-scoped service with its transaction-scoped session."""

    settings = request.app.state.settings
    cache = TicketCache(
        getattr(request.app.state, "redis", None),
        ttl_seconds=settings.ticket_cache_ttl_seconds,
    )
    return TicketService(
        session,
        cache=cache,
        current_user=user,
        background_processing_enabled=getattr(
            settings, "background_processing_enabled", True
        ),
    )


TicketServiceDep = Annotated[TicketService, Depends(get_ticket_service)]
