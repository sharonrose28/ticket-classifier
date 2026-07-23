"""Create or promote the initial administrator account."""

import argparse
import asyncio
import getpass
from app.core.security import hash_password
from app.db.session import get_session_factory, dispose_engine
from app.models.user import User, UserRole
from app.repositories.users import UserRepository


async def create_admin(email: str, full_name: str, password: str) -> None:
    async with get_session_factory()() as session:
        repository = UserRepository(session)
        user = await repository.get_by_email(email)
        if user is None:
            user = User(full_name=full_name, email=email.casefold(), password_hash=hash_password(password))
            session.add(user)
        user.role = UserRole.ADMIN
        user.is_active = True
        await session.commit()
        print(f"Administrator ready: {user.email}")
    await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args()
    secret = getpass.getpass("Admin password: ")
    if len(secret) < 12:
        raise SystemExit("Password must be at least 12 characters")
    asyncio.run(create_admin(args.email, args.name, secret))
