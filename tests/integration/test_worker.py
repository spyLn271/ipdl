from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import respx
from sqlalchemy import select

from ipdl.analysis.methodology import load_jurisdictions, load_risk_model
from ipdl.analysis.pipeline import Deps
from ipdl.api import worker
from ipdl.api.state import AppState
from ipdl.db.models import AuditEvent, JobStatus, Person, SanctionsList
from ipdl.db.models import Portrait as PortraitRow
from ipdl.db.session import Database
from ipdl.fetch.fetcher import Fetcher
from ipdl.llm.extract import FactExtractor
from ipdl.search.collect import load_plan
from ipdl.search.searxng import SearxngClient
from tests.conftest import make_settings
from tests.fakes import FakeLLM, FakeQueue, FakeScreener, match
from tests.integration.test_sanctions_db import mock_lists
from tests.sample import LLM_ANSWERS, SUBJECT, mock_web

pytestmark = pytest.mark.db


async def _allow(url: str) -> None:
    return None


def _ctx(db: Database, *, llm: FakeLLM | None = None) -> dict[str, Any]:
    settings = make_settings()
    searx, fetcher = SearxngClient(settings.search), Fetcher(settings.fetch)
    return {
        "settings": settings,
        "db": db,
        "searxng": searx,
        "fetcher": fetcher,
        "llm": None,
        "state": AppState(settings=settings, db=db, queue=FakeQueue()),
        "deps": Deps(
            settings=settings,
            plan=load_plan(settings.search.queries_file),
            model=load_risk_model(settings.methodology_file),
            jurisdictions=load_jurisdictions(settings.jurisdictions_file),
            searxng=searx,
            fetcher=fetcher,
            extractor=FactExtractor(llm or FakeLLM(LLM_ANSWERS)),
            sanctions=FakeScreener({SUBJECT.full_name: [match("PETR SERGEEVICH IVANOV")]}),
        ),
    }


async def _queued(db: Database) -> tuple[uuid.UUID, uuid.UUID]:
    async with db.session() as session:
        person = Person(
            full_name=SUBJECT.full_name, birth_date=SUBJECT.birth_date, context=SUBJECT.context
        )
        session.add(person)
        await session.flush()
        row = PortraitRow(
            person_id=person.id,
            version=1,
            status=JobStatus.QUEUED,
            params=SUBJECT.model_dump(mode="json"),
        )
        session.add(row)
        await session.flush()
        return person.id, row.id


async def test_build_job_success(clean_db: Database) -> None:
    person_id, portrait_id = await _queued(clean_db)
    ctx = _ctx(clean_db)
    with (
        respx.mock(assert_all_called=False) as router,
        patch("ipdl.fetch.fetcher.assert_public_url", _allow),
    ):
        mock_web(router)
        await worker.build_portrait_job(ctx, str(portrait_id))
        # Повторный запуск уже построенной версии ничего не делает
        await worker.build_portrait_job(ctx, str(portrait_id))
    await worker.shutdown(ctx)

    async with clean_db.session() as session:
        row = await session.get(PortraitRow, portrait_id)
        person = await session.get(Person, person_id)
        actions = (await session.scalars(select(AuditEvent.action))).all()
    assert row is not None and row.status is JobStatus.DONE and row.progress == 100
    assert row.data is not None and row.data["pep"]["category"] == "foreign"
    assert person is not None and person.current_portrait_id == portrait_id
    assert person.risk_level == "high" and person.pep_category == "foreign"
    assert person.position == "Министр финансов"
    assert "portrait_built" in actions


async def test_build_job_failure(clean_db: Database) -> None:
    _, portrait_id = await _queued(clean_db)
    ctx = _ctx(clean_db)

    async def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("сбой")

    with patch.object(worker, "build_portrait", boom):
        await worker.build_portrait_job(ctx, str(portrait_id))
    await worker.shutdown(ctx)
    async with clean_db.session() as session:
        row = await session.get(PortraitRow, portrait_id)
    assert row is not None and row.status is JobStatus.FAILED
    assert row.error == "Ошибка построения портрета: RuntimeError"


async def test_stale_jobs_are_recovered(clean_db: Database) -> None:
    _, portrait_id = await _queued(clean_db)
    async with clean_db.session() as session:
        row = await session.get(PortraitRow, portrait_id)
        assert row is not None
        row.status = JobStatus.RUNNING
        row.started_at = datetime.now(UTC) - timedelta(hours=5)
    await worker._recover_stale(clean_db, make_settings())
    async with clean_db.session() as session:
        row = await session.get(PortraitRow, portrait_id)
    assert row is not None and row.status is JobStatus.FAILED and "прервано" in (row.error or "")


async def test_sanctions_jobs(clean_db: Database) -> None:
    ctx = {"db": clean_db, "settings": make_settings()}
    with respx.mock() as router:
        mock_lists(router)
        await worker.startup_sanctions_if_empty(ctx)
        result = await worker.update_sanctions_job(ctx)
    assert result == {"un": 3, "ofac_sdn": 2, "eu": 2, "uk": 1}
    async with clean_db.session() as session:
        loaded = (
            await session.scalars(select(SanctionsList).where(SanctionsList.entries > 0))
        ).all()
    assert len(loaded) == 4
    # Списки уже загружены — повторная начальная загрузка не выполняется (сеть не нужна)
    with respx.mock(assert_all_called=False) as router:
        network = router.route().mock(return_value=httpx.Response(500))
        await worker.startup_sanctions_if_empty(ctx)
    assert network.call_count == 0
    await worker.purge_sessions(ctx)
