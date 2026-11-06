from __future__ import annotations

import io
import zipfile

import docx

from ipdl.analysis.model import (
    FactorKey,
    PepCategory,
    PepTenure,
    Review,
    RiskLevel,
)
from ipdl.config.settings import OrgSettings, Settings
from ipdl.report.render import render_docx, render_html, render_pdf
from tests.fakes import FakeLLM, FakeScreener
from tests.sample import LLM_ANSWERS, NEWS_URL, WIKI_URL, build_sample


async def test_pipeline_builds_full_portrait(settings: Settings) -> None:
    portrait = await build_sample(settings)

    # Источники: нерелевантная ссылка и соцсеть отброшены, страницы загружены
    urls = {s.url for s in portrait.sources}
    assert WIKI_URL in urls and NEWS_URL in urls
    assert not any("weather" in u or "facebook" in u for u in urls)
    assert portrait.stats.fetched == 3
    assert portrait.stats.analyzed == 3
    assert portrait.stats.llm_used

    # Идентификация: дата рождения аналитика подтверждена источником, гражданство из текста
    assert portrait.identity.birth_date is not None
    assert portrait.identity.birth_date.value == "1970-03-05"
    assert portrait.identity.citizenship == ["BY"]

    # Должность из двух источников объединена; статус — действующее ИПДЛ (абз. 6)
    assert len(portrait.positions) == 1
    assert len(portrait.positions[0].evidence) == 2
    assert portrait.pep.category is PepCategory.FOREIGN
    assert portrait.pep.tenure is PepTenure.CURRENT
    assert portrait.pep.clause is not None and "абз. 6" in portrait.pep.clause

    # Связи: описание «Три сына» отброшено, событие с выдуманной цитатой — тоже
    assert [r.name for r in portrait.relations] == ["Анна Иванова"]
    assert all(e.summary != "Получил орден" for e in portrait.timeline)

    # Риск: совпадение с санкционным списком → минимум 85, высокий уровень
    factors = {f.key: f.level for f in portrait.risk.factors}
    assert factors[FactorKey.SANCTIONS] is RiskLevel.HIGH
    assert factors[FactorKey.LEGAL] is RiskLevel.HIGH
    assert factors[FactorKey.POSITION] is RiskLevel.HIGH
    assert portrait.risk.score >= 85
    assert portrait.risk.level is RiskLevel.HIGH
    assert portrait.risk.floors

    assert "Иванов Пётр Сергеевич" in portrait.conclusion
    assert portrait.limitations
    # SearXNG сообщал о недоступном поисковике во всех запросах — это попадает в предупреждения
    assert "Поисковики отвечали с ошибками: duckduckgo." in portrait.warnings


async def test_pipeline_survives_search_and_llm_outage(settings: Settings) -> None:
    portrait = await build_sample(
        settings,
        llm=FakeLLM(LLM_ANSWERS, fail_on="Источник"),
        screener=FakeScreener(lists=[]),
        searx_down=True,
    )
    assert portrait.sources == []
    assert not portrait.stats.search_ok
    assert portrait.pep.category is PepCategory.UNDETERMINED
    warnings = " ".join(portrait.warnings)
    assert "SearXNG недоступен" in warnings
    assert "Санкционные списки не загружены" in warnings
    factors = {f.key: f.level for f in portrait.risk.factors}
    assert factors[FactorKey.SANCTIONS] is RiskLevel.NO_DATA
    assert factors[FactorKey.ADVERSE_MEDIA] is RiskLevel.NO_DATA


async def test_pipeline_reports_llm_failures(settings: Settings) -> None:
    portrait = await build_sample(settings, llm=FakeLLM(LLM_ANSWERS, fail_on="news.example.com"))
    assert portrait.stats.analyzed == 2
    assert any("не обработала 1 из 3" in w for w in portrait.warnings)


async def test_progress_is_monotonic(settings: Settings) -> None:
    from unittest.mock import patch

    import respx

    from ipdl.analysis.methodology import load_jurisdictions, load_risk_model
    from ipdl.analysis.pipeline import Deps, Stage, build_portrait
    from ipdl.fetch.fetcher import Fetcher
    from ipdl.llm.extract import FactExtractor
    from ipdl.search.collect import load_plan
    from ipdl.search.searxng import SearxngClient
    from tests.sample import SUBJECT, mock_web

    seen: list[tuple[Stage, int]] = []

    async def progress(stage: Stage, percent: int) -> None:
        seen.append((stage, percent))

    async def allow(url: str) -> None:
        return None

    with (
        respx.mock(assert_all_called=False) as router,
        patch("ipdl.fetch.fetcher.assert_public_url", allow),
    ):
        mock_web(router)
        searx, fetcher = SearxngClient(settings.search), Fetcher(settings.fetch)
        deps = Deps(
            settings=settings,
            plan=load_plan(settings.search.queries_file),
            model=load_risk_model(settings.methodology_file),
            jurisdictions=load_jurisdictions(settings.jurisdictions_file),
            searxng=searx,
            fetcher=fetcher,
            extractor=FactExtractor(FakeLLM(LLM_ANSWERS)),
            sanctions=FakeScreener(),
        )
        await build_portrait(SUBJECT, deps, progress)
        await searx.aclose()
        await fetcher.aclose()
    percents = [p for _, p in seen]
    assert percents == sorted(percents)
    assert seen[-1] == (Stage.ASSESS, 100)
    assert {s for s, _ in seen} == set(Stage)


# ---------------------------------------------------------------- экспорт


async def test_exports(settings: Settings) -> None:
    portrait = await build_sample(settings)
    review = Review(reviewer="Аналитик", conclusion="Итог")
    org = OrgSettings()

    content = render_docx(portrait, review=review, org=org, version=2)
    assert zipfile.is_zipfile(io.BytesIO(content))
    document = docx.Document(io.BytesIO(content))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "АНАЛИТИЧЕСКИЙ ПОРТРЕТ" in text
    assert "Иванов Пётр Сергеевич — предварительная AML/KYC-оценка" in text
    assert "3. Предварительная оценка статуса ИПДЛ" in text
    assert "10. Источники для верификации" in text
    table = document.tables[0]
    assert table.rows[0].cells[0].text == "Параметр"
    assert table.rows[-1].cells[0].text == "Итоговый AML-риск"

    html = render_html(portrait, review=review, org=org, version=2)
    assert "Иванов Пётр Сергеевич" in html
    assert "Факторы риска" in html
    assert "<script" not in html

    pdf = await render_pdf(portrait, review=review, org=org, version=2)
    assert pdf.startswith(b"%PDF")
