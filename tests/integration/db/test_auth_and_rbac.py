import uuid

import pytest

from app.core.exceptions import AuthorizationError, EmailAlreadyExistsError, InvalidCredentialsError
from app.models.ticket import TicketStatus
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, SignUpRequest
from app.schemas.ticket import ClassificationCorrection, TicketCreate, TicketRead
from app.services.auth_service import AuthService
from app.services.ticket_service import TicketService


def signup(email="alex@example.com"):
    return SignUpRequest(
        full_name="Alex Morgan",
        email=email,
        password="StrongPassword1",
        confirm_password="StrongPassword1",
    )


@pytest.mark.asyncio
async def test_registration_login_and_duplicate_email(session):
    service = AuthService(session)
    user = await service.register(signup())
    assert user.role is UserRole.CUSTOMER
    assert user.password_hash != "StrongPassword1"
    assert (
        await service.authenticate(
            LoginRequest(email="alex@example.com", password="StrongPassword1")
        )
    ).id == user.id
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(
            LoginRequest(email="alex@example.com", password="WrongPassword1")
        )
    with pytest.raises(InvalidCredentialsError):
        await service.authenticate(
            LoginRequest(email="missing@example.com", password="StrongPassword1")
        )
    with pytest.raises(EmailAlreadyExistsError):
        await service.register(signup("ALEX@example.com"))


@pytest.mark.asyncio
async def test_customer_can_only_access_owned_tickets(session):
    customer = User(
        full_name="Customer",
        email="customer@example.com",
        password_hash="x",
        role=UserRole.CUSTOMER,
    )
    other = User(
        full_name="Other", email="other@example.com", password_hash="x", role=UserRole.CUSTOMER
    )
    session.add_all([customer, other])
    await session.commit()
    service = TicketService(session, task_dispatcher=lambda _id: None, current_user=customer)
    owned = await service.create(TicketCreate(title="Mine", description="Owned ticket"))
    foreign = await TicketService(
        session, task_dispatcher=lambda _id: None, current_user=other
    ).create(TicketCreate(title="Other", description="Foreign ticket"))
    items, total = await service.list(limit=10, offset=0)
    assert total == 1 and items[0].id == owned.id
    with pytest.raises(AuthorizationError):
        await service.get(foreign.id)


@pytest.mark.asyncio
async def test_agent_can_mutate_only_assigned_ticket_and_admin_can_assign(session):
    customer = User(
        full_name="Customer", email="c@example.com", password_hash="x", role=UserRole.CUSTOMER
    )
    agent = User(
        full_name="Agent", email="a@example.com", password_hash="x", role=UserRole.SUPPORT_AGENT
    )
    other_agent = User(
        full_name="Other agent",
        email="o@example.com",
        password_hash="x",
        role=UserRole.SUPPORT_AGENT,
    )
    admin = User(
        full_name="Admin", email="admin@example.com", password_hash="x", role=UserRole.ADMIN
    )
    session.add_all([customer, agent, other_agent, admin])
    await session.commit()
    ticket = await TicketService(
        session, task_dispatcher=lambda _id: None, current_user=customer
    ).create(TicketCreate(title="Help", description="Need help"))
    admin_service = TicketService(session, task_dispatcher=lambda _id: None, current_user=admin)
    await admin_service.assign(ticket.id, agent.id)
    # Server-generated updated_at must be eagerly available to FastAPI after commit.
    TicketRead.model_validate(ticket)
    agent_service = TicketService(session, task_dispatcher=lambda _id: None, current_user=agent)
    assert (await agent_service.list(limit=10, offset=0))[1] == 1
    await agent_service.update_status(ticket.id, TicketStatus.PROCESSING)
    TicketRead.model_validate(ticket)
    corrected = await agent_service.correct_classification(
        ticket.id,
        ClassificationCorrection(
            urgency="high", category="billing", confidence=0.9, reasoning="Billing impact"
        ),
    )
    TicketRead.model_validate(corrected)
    assert corrected.category == "billing" and corrected.assigned_queue == "support"
    with pytest.raises(AuthorizationError):
        await TicketService(
            session, task_dispatcher=lambda _id: None, current_user=other_agent
        ).update_status(ticket.id, TicketStatus.COMPLETE)
    inactive = User(
        full_name="Inactive",
        email="inactive@example.com",
        password_hash="x",
        role=UserRole.SUPPORT_AGENT,
        is_active=False,
    )
    session.add(inactive)
    await session.commit()
    with pytest.raises(AuthorizationError):
        await admin_service.assign(ticket.id, inactive.id)


@pytest.mark.asyncio
async def test_agent_cannot_create_customer_ticket(session):
    agent = User(
        id=uuid.uuid4(),
        full_name="Agent",
        email="agent@example.com",
        password_hash="x",
        role=UserRole.SUPPORT_AGENT,
    )
    session.add(agent)
    await session.commit()
    with pytest.raises(AuthorizationError):
        await TicketService(session, task_dispatcher=lambda _id: None, current_user=agent).create(
            TicketCreate(title="x", description="y")
        )
