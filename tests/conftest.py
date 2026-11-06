"""Общие фикстуры. Тесты с маркером ``db`` требуют PostgreSQL: IPDL_TEST_DATABASE_URL."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from ipdl.config.settings import Environment, Settings
from ipdl.db.session import Database

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEST_DB_ENV = "IPDL_TEST_DATABASE_URL"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "env": Environment.TEST,
        "methodology_file": ROOT / "methodology/risk-model.yaml",
        "jurisdictions_file": ROOT / "methodology/jurisdictions.yaml",
        "search": {
            "base_url": "http://searxng.test",
            "queries_file": ROOT / "methodology/search-queries.yaml",
            "stagger_s": 0,
        },
        "sanctions": {"sources_file": ROOT / "methodology/sanctions-sources.yaml"},
        "fetch": {"respect_robots_txt": True},
        "auth": {"cookie_secure": False, "min_password_length": 12},
        "db": {"url": os.environ.get(TEST_DB_ENV, "postgresql+asyncpg://u:p@localhost:1/none")},
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


# ---------------------------------------------------------------- PostgreSQL


@pytest.fixture(scope="session")
async def database() -> AsyncIterator[Database]:
    url = os.environ.get(TEST_DB_ENV)
    if not url:
        pytest.skip(f"{TEST_DB_ENV} не задан — тесты с PostgreSQL пропущены")
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()

    from alembic import command
    from alembic.config import Config

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["url"] = url
    import asyncio

    # env.py запускает свой цикл asyncio — выполняем миграции в отдельном потоке
    await asyncio.to_thread(command.upgrade, config, "head")
    db = Database(make_settings().db)
    yield db
    await db.dispose()


@pytest.fixture
async def clean_db(database: Database) -> Database:
    async with database.engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                    "AND tablename <> 'alembic_version'"
                )
            )
        ).scalars()
        await conn.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    return database


# ---------------------------------------------------------------- API


@pytest.fixture
async def api(clean_db: Database) -> AsyncIterator[tuple[httpx.AsyncClient, Any]]:
    from ipdl.api.app import create_app
    from tests.fakes import FakeQueue

    queue = FakeQueue()
    app = create_app(make_settings(), db=clean_db, queue=queue)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, app
