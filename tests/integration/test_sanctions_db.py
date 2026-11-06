from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx
from sqlalchemy import func, select

from ipdl.config.settings import SanctionsSettings
from ipdl.db.models import SanctionsEntryRow, SanctionsList, SanctionsName
from ipdl.db.session import Database
from ipdl.sanctions.service import DbScreener, SanctionsUpdater, load_sources, screen
from tests.conftest import FIXTURES, ROOT

pytestmark = pytest.mark.db

SOURCES = load_sources(ROOT / "methodology/sanctions-sources.yaml")
FILES = {"un": "un.xml", "ofac_sdn": "ofac.xml", "eu": "eu.xml", "uk": "uk.xml"}


def _settings() -> SanctionsSettings:
    return SanctionsSettings(sources_file=ROOT / "methodology/sanctions-sources.yaml")


def mock_lists(router: respx.MockRouter, *, failing: str | None = None) -> None:
    for source in SOURCES:
        route = router.get(source.url)
        if source.id == failing:
            route.mock(return_value=httpx.Response(500))
        else:
            body = (FIXTURES / "sanctions" / FILES[source.id]).read_bytes()
            route.mock(return_value=httpx.Response(200, content=body))


async def load_fixture_lists(db: Database) -> None:
    with respx.mock() as router:
        mock_lists(router)
        await SanctionsUpdater(db, _settings()).update_all()


async def test_update_screen_and_unchanged(clean_db: Database) -> None:
    updater = SanctionsUpdater(clean_db, _settings())
    with respx.mock() as router:
        mock_lists(router, failing="uk")
        results = {r.list_id: r for r in await updater.update_all()}
    assert results["un"].status == "updated" and results["un"].entries == 3
    assert results["ofac_sdn"].entries == 2
    assert results["uk"].status == "error"

    async with clean_db.session() as session:
        assert await session.scalar(select(func.count()).select_from(SanctionsEntryRow)) == 7
        names = await session.scalar(select(func.count()).select_from(SanctionsName))
        assert names is not None and names >= 10
        uk = await session.get(SanctionsList, "uk")
        assert uk is not None and uk.status == "error" and uk.error
        un = await session.get(SanctionsList, "un")
        assert un is not None and un.published_at == date(2026, 10, 26)

    # Повторная загрузка того же файла: «unchanged», записи не дублируются
    with respx.mock() as router:
        mock_lists(router)
        results = {r.list_id: r for r in await updater.update_all()}
    assert results["un"].status == "unchanged"
    assert results["uk"].status == "updated"

    screener = DbScreener(clean_db, _settings())
    matches = await screener.screen(
        ["Тестман Виктор Владимирович"], birth_date=date(1958, 5, 26), entity_types=("person",)
    )
    assert {m.list_id for m in matches} == {"ofac_sdn", "eu", "uk"}
    assert all(m.dob_match for m in matches)
    ofac = next(m for m in matches if m.list_id == "ofac_sdn")
    assert ofac.url == "https://sanctionssearch.ofac.treas.gov/Details.aspx?id=9001"

    wrong_dob = await screener.screen(
        ["Viktor Testman"], birth_date=date(1990, 1, 1), entity_types=("person",)
    )
    assert wrong_dob and all(m.dob_match is False for m in wrong_dob)

    assert await screener.screen(["Тимур Турлов"], birth_date=None, entity_types=("person",)) == []

    companies = await screener.screen(
        ["Northwind Trading LLP"], birth_date=None, entity_types=("entity",)
    )
    assert {m.list_id for m in companies} == {"un", "eu"}
    assert await screener.screen(["Freedom Bank"], birth_date=None, entity_types=("entity",)) == []

    lists = await screener.lists()
    assert {s.id for s in lists} == {"un", "ofac_sdn", "eu", "uk"}


async def test_screen_ignores_short_queries(clean_db: Database) -> None:
    await load_fixture_lists(clean_db)
    async with clean_db.session() as session:
        assert await screen(session, ["", "  ", "Ab"]) == []
