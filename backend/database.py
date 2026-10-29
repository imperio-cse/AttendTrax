# =============================================================================
# AttendTrax Enterprise – Database Connection & Session Lifecycle
# database.py  –  Async SQLAlchemy Engine & Session Factory (Supabase & SQLite)
# =============================================================================
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from config import get_settings

Base = declarative_base()

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = get_settings().get_database_url()
        connect_args = {}
        if db_url.startswith("sqlite"):
            # SQLite needs connect_args check_same_thread=False
            connect_args = {"check_same_thread": False}
            _engine = create_async_engine(
                db_url,
                echo=False,
                connect_args=connect_args,
            )
        else:
            # PostgreSQL / Supabase pool settings
            # If using Supabase transaction pooler (port 6543), asyncpg requires statement_cache_size=0
            if ":6543" in db_url or "pooler.supabase.com" in db_url:
                connect_args["statement_cache_size"] = 0
            _engine = create_async_engine(
                db_url,
                echo=False,
                pool_size=10,
                max_overflow=5,
                pool_recycle=300,
                pool_pre_ping=True,
                connect_args=connect_args,
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency for database session injection."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all database tables if they do not exist."""
    engine = get_engine()
    async with engine.begin() as conn:
        # Import models so Base metadata has all table definitions
        import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
