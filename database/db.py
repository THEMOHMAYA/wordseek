import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy import event, text
from config.settings import settings
from database.models import Base

connect_args = {}
if "sqlite" in settings.ASYNC_DATABASE_URL:
    connect_args["timeout"] = 30

engine: AsyncEngine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args
)

if "sqlite" in settings.ASYNC_DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession
)

async def init_db():
    """Initializes the database schema and cleans up any orphaned guesses."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Clean up any orphaned guesses from previously interrupted games
        try:
            await conn.execute(text("DELETE FROM guesses WHERE game_id NOT IN (SELECT id FROM games);"))
        except Exception:
            pass

@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for acquiring a database session."""
    session: AsyncSession = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
