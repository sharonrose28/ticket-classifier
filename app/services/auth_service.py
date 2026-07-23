"""Registration and credential verification use cases."""

import asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import EmailAlreadyExistsError, InvalidCredentialsError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest, SignUpRequest


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, payload: SignUpRequest) -> User:
        if await self.users.get_by_email(payload.email):
            raise EmailAlreadyExistsError()
        password_hash = await asyncio.to_thread(hash_password, payload.password)
        try:
            user = await self.users.create(full_name=payload.full_name, email=payload.email, password_hash=password_hash)
            await self.session.commit()
            return user
        except IntegrityError as exc:
            await self.session.rollback()
            raise EmailAlreadyExistsError() from exc

    async def authenticate(self, payload: LoginRequest) -> User:
        user = await self.users.get_by_email(payload.email)
        if user is None or not user.is_active:
            raise InvalidCredentialsError()
        if not await asyncio.to_thread(verify_password, payload.password, user.password_hash):
            raise InvalidCredentialsError()
        return user
