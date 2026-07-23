import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api import dependencies
from app.api.v1.endpoints import admin, auth
from app.core.exceptions import AuthenticationError, AuthorizationError, UserNotFoundError
from app.core.security import create_access_token
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, SignUpRequest
from app.schemas.user import UserActiveUpdate, UserRoleUpdate


def settings():
    return SimpleNamespace(
        jwt_secret_key=SimpleNamespace(get_secret_value=lambda: "a-test-secret-that-is-long-enough-for-jwt"),
        jwt_access_token_minutes=10,
        auth_cookie_name="support_session",
        auth_cookie_secure=False,
        ticket_cache_ttl_seconds=30,
    )


def request(cookie=None):
    headers = [] if cookie is None else [(b"cookie", f"support_session={cookie}".encode())]
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": headers})
    req.scope["app"] = SimpleNamespace(state=SimpleNamespace(settings=settings(), redis=None))
    return req


@pytest.mark.asyncio
async def test_auth_endpoint_functions(session, monkeypatch):
    user = User(full_name="Alex", email="alex@example.com", password_hash="hash", role=UserRole.CUSTOMER)
    session.add(user)
    await session.commit()

    class FakeAuthService:
        def __init__(self, _session): pass
        async def register(self, _payload): return user
        async def authenticate(self, _payload): return user

    monkeypatch.setattr(auth, "AuthService", FakeAuthService)
    registered = await auth.signup(SignUpRequest(full_name="Alex", email="alex@example.com", password="StrongPassword1", confirm_password="StrongPassword1"), session)
    response = Response()
    logged_in = await auth.login(LoginRequest(email="alex@example.com", password="StrongPassword1"), request(), response, session)
    assert registered.id == logged_in.id
    assert "support_session=" in response.headers["set-cookie"] and "HttpOnly" in response.headers["set-cookie"]
    assert (await auth.me(user)).id == user.id
    logout_response = Response()
    await auth.logout(request(), logout_response)
    assert "support_session=" in logout_response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_authentication_and_role_dependencies(session):
    user = User(full_name="Admin", email="admin@example.com", password_hash="hash", role=UserRole.ADMIN)
    session.add(user)
    await session.commit()
    token = create_access_token(subject=user.id, secret=settings().jwt_secret_key.get_secret_value(), lifetime_seconds=60)
    assert (await dependencies.get_current_user(request(token), session)).id == user.id
    with pytest.raises(AuthenticationError):
        await dependencies.get_current_user(request("invalid"), session)
    allow_admin = dependencies.require_roles(UserRole.ADMIN)
    deny_customer = dependencies.require_roles(UserRole.CUSTOMER)
    assert await allow_admin(user) is user
    with pytest.raises(AuthorizationError):
        await deny_customer(user)
    service = dependencies.get_ticket_service(request(), session, user)
    assert service.current_user is user


@pytest.mark.asyncio
async def test_admin_endpoint_functions(session):
    user = User(full_name="Agent", email="agent@example.com", password_hash="hash", role=UserRole.CUSTOMER)
    session.add(user)
    await session.flush()
    session.add(Ticket(title="Help", description="Issue", customer_id=user.id, status=TicketStatus.PENDING))
    await session.commit()
    users = await admin.list_users(session)
    assert len(users) == 1
    changed = await admin.change_role(user.id, UserRoleUpdate(role=UserRole.SUPPORT_AGENT), session)
    assert changed.role is UserRole.SUPPORT_AGENT
    disabled = await admin.change_active(user.id, UserActiveUpdate(is_active=False), session)
    assert disabled.is_active is False
    data = await admin.analytics(session)
    assert data["users"] == 1 and data["tickets"] == 1 and data["tickets_by_status"]["pending"] == 1
    missing = uuid.uuid4()
    with pytest.raises(UserNotFoundError):
        await admin.change_role(missing, UserRoleUpdate(role=UserRole.ADMIN), session)
    with pytest.raises(UserNotFoundError):
        await admin.change_active(missing, UserActiveUpdate(is_active=True), session)
