"""Administrator-only user management and analytics."""

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from app.api.dependencies import SessionDep, require_roles
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User, UserRole
from app.repositories.users import UserRepository
from app.schemas.user import UserActiveUpdate, UserRead, UserRoleUpdate
from app.core.exceptions import UserNotFoundError

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_roles(UserRole.ADMIN))])


@router.get("/users", response_model=list[UserRead])
async def list_users(session: SessionDep) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in await UserRepository(session).list()]


@router.patch("/users/{user_id}/role", response_model=UserRead)
async def change_role(user_id: uuid.UUID, payload: UserRoleUpdate, session: SessionDep) -> UserRead:
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError()
    user.role = payload.role
    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)


@router.patch("/users/{user_id}/active", response_model=UserRead)
async def change_active(user_id: uuid.UUID, payload: UserActiveUpdate, session: SessionDep) -> UserRead:
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError()
    user.is_active = payload.is_active
    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)


@router.get("/analytics")
async def analytics(session: SessionDep) -> dict:
    users = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    tickets = int(await session.scalar(select(func.count()).select_from(Ticket)) or 0)
    rows = await session.execute(select(Ticket.status, func.count()).group_by(Ticket.status))
    by_status = {status.value: count for status, count in rows.all()}
    return {"users": users, "tickets": tickets, "tickets_by_status": {status.value: by_status.get(status.value, 0) for status in TicketStatus}}
