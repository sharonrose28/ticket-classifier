"""User persistence operations."""

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email.casefold()))

    async def create(self, *, full_name: str, email: str, password_hash: str) -> User:
        user = User(full_name=full_name, email=email.casefold(), password_hash=password_hash, role=UserRole.CUSTOMER)
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def list(self) -> list[User]:
        result = await self.session.scalars(select(User).order_by(User.created_at.desc()))
        return list(result.all())
