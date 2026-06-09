"""Integration test fixtures — spins up a real Postgres via testcontainers."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_url(postgres_container: PostgresContainer) -> str:
    sync_url = postgres_container.get_connection_url()
    return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session", autouse=True)
def run_migrations(postgres_container: PostgresContainer, db_url: str) -> None:
    """Run alembic migrations against the test Postgres instance."""
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    env = {**os.environ, "DATABASE_URL": sync_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic migrations failed:\n{result.stderr}")


@pytest.fixture
async def db_session(db_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        try:
            yield session
            await session.rollback()  # always roll back in tests for isolation
        finally:
            await session.close()
    await engine.dispose()
