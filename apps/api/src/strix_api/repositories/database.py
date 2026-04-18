"""SQLAlchemy async engine + session helpers.

One engine per process. Sessions come from a `sessionmaker` and are
returned via `async with session_scope()` (manual scope) or via the
FastAPI dep `get_db_session()` (auto scope).

Pool is configured from `Settings.db` (§7.7): 10 + 5 overflow per replica.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from strix_api.observability import get_logger
from strix_api.settings import Settings

log = get_logger("strix_api.repositories.database")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(settings: Settings) -> AsyncEngine:
    """Idempotent — returns the same engine on repeated calls."""
    global _engine, _sessionmaker
    if _engine is not None:
        return _engine

    db = settings.db
    _engine = create_async_engine(
        db.dsn,
        pool_size=db.pool_size,
        max_overflow=db.max_overflow,
        pool_timeout=db.pool_timeout_seconds,
        pool_recycle=db.pool_recycle_seconds,
        pool_pre_ping=True,
        echo=False,
    )
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    log.info(
        "db_engine_ready",
        host=db.host,
        port=db.port,
        name=db.name,
        pool_size=db.pool_size,
    )
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_engine(settings) must be called before get_sessionmaker()")
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Worker-friendly: explicit `async with` boundary for one transaction."""
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


__all__ = [
    "dispose_engine",
    "get_sessionmaker",
    "init_engine",
    "session_scope",
]
