import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# Supabase's pooled connection (port 6543, pgbouncer/Supavisor transaction mode) does
# not support server-side prepared statements the way a direct connection does: a
# "logical" asyncpg connection can be handed a backend socket that a *different* prior
# logical connection already prepared statements on, without clearing them first. Both
# asyncpg's own default name counter and SQLAlchemy's default name counter restart at
# "__asyncpg_stmt_1__" for every new logical connection, so disabling caching alone
# (statement_cache_size / prepared_statement_cache_size = 0) isn't enough - the name
# itself still collides with a leftover statement on the reused backend. Per SQLAlchemy's
# asyncpg dialect docs, the actual fix is a name function that can never repeat.
engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
    },
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
