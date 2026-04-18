"""User lookup + creation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from strix_api.repositories.models import User


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._s.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._s.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        role: str = "admin",
        designation: str | None = None,
    ) -> User:
        user = User(
            user_id=uuid4(),
            email=email.lower().strip(),
            password_hash=password_hash,
            role=role,
            is_active=True,
            designation=designation,
        )
        self._s.add(user)
        await self._s.flush()
        return user

    async def update_password(self, user_id: UUID, password_hash: str) -> None:
        u = await self._s.get(User, user_id)
        if u is None:
            return
        u.password_hash = password_hash
        u.updated_at = datetime.now(timezone.utc)
        await self._s.flush()

    async def list_active(self) -> list[User]:
        result = await self._s.execute(
            select(User).where(User.is_active.is_(True))
        )
        return list(result.scalars().all())


__all__ = ["UserRepo"]
