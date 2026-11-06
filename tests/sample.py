"""Сквозной тестовый сценарий: вымышленный министр иностранного государства.

Выдача SearXNG, страницы и ответы «модели» согласованы между собой: цитаты из ответов
модели действительно есть в текстах страниц, поэтому проходят проверку цитат.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import httpx
import respx

from ipdl.analysis.methodology import load_jurisdictions, load_risk_model
from ipdl.analysis.model import Portrait, Subject
from ipdl.analysis.pipeline import Deps, build_portrait
from ipdl.config.settings import Settings
from ipdl.fetch.fetcher import Fetcher
from ipdl.llm.extract import FactExtractor
from ipdl.search.collect import load_plan
from ipdl.search.searxng import SearxngClient
from tests.fakes import FakeLLM, FakeScreener, match

SEARX = "http://searxng.test"
SUBJECT = Subject(
    full_name="Иванов Пётр Сергеевич",
    birth_date=date(1970, 3, 5),
    context="Министерство финансов Беларуси",
)

WIKI_URL = "https://ru.wikipedia.org/wiki/Иванов,_Пётр_Сергеевич"
NEWS_URL = "https://news.example.com/2022/ivanov-case"
GOV_URL = "https://www.minfin.gov.by/ru/about/ivanov"

PAGES: dict[str, str] = {
    WIKI_URL: """<html><head><title>Иванов, Пётр Сергеевич — Википедия</title></head><body>
<main><article><h1>Иванов, Пётр Сергеевич</h1>
<p>Пётр Серге́евич Ивано́в (род. 5 марта 1970 года в Минске)[1] — белорусский государственный
деятель, с 2019 года занимает пост министра финансов Республики Беларусь.</p>
<p>Окончил Белорусский государственный экономический университет в 1992 году.</p>
<p>Супруга Петра Иванова — Анна Иванова, владеет кипрской компанией Alfa Holdings Ltd.</p>
<p>[править | править код]</p>
</article></main></body></html>""",
    NEWS_URL: """<html><head><title>Против Петра Иванова возбуждено дело</title></head><body>
<article><h1>Против Петра Иванова возбуждено уголовное дело</h1>
<p>В 2022 году против министра Петра Иванова возбуждено уголовное дело о получении взятки
в особо крупном размере, сообщила прокуратура.</p>
<p>Иванов свою вину не признаёт.</p></article></body></html>""",
    GOV_URL: """<html><head><title>Министр финансов — Иванов Пётр Сергеевич</title></head><body>
<main><h1>Министр финансов Иванов Пётр Сергеевич</h1>
<p>Иванов Пётр Сергеевич назначен министром финансов Республики Беларусь указом Президента
в 2019 году.</p></main></body></html>""",
}

LLM_ANSWERS: dict[str, dict[str, Any]] = {
    "(ru.wikipedia.org)": {
        "about_subject": "yes",
        "birth_date": {"value": "1970-03-05", "quote": "род. 5 марта 1970 года в Минске"},
        "birth_place": {"value": "Минск", "quote": "род. 5 марта 1970 года в Минске"},
        "citizenship": [{"country": "BY", "quote": "белорусский государственный деятель"}],
        "positions": [
            {
                "title": "Министр финансов",
                "organization": "Министерство финансов Республики Беларусь",
                "country": "BY",
                "start": "2019",
                "end": "",
                "current": "yes",
                "category": "state_body",
                "quote": "с 2019 года занимает пост министра финансов Республики Беларусь",
            }
        ],
        "relations": [
            {
                "name": "Анна Иванова",
                "relation": "spouse",
                "note": "владеет Alfa Holdings Ltd",
                "public_official": "no",
                "quote": "Супруга Петра Иванова — Анна Иванова, владеет кипрской компанией",
            },
            # Описание вместо имени — должно быть отброшено
            {
                "name": "Три сына",
                "relation": "child",
                "note": "",
                "public_official": "no",
                "quote": "Супруга Петра Иванова — Анна Иванова",
            },
        ],
        "companies": [],
        "adverse": [],
        "legal": [],
        "events": [
            {
                "date": "1992",
                "summary": "Окончил БГЭУ",
                "quote": (
                    "Окончил Белорусский государственный экономический университет в 1992 году"
                ),
            },
            # Выдуманная цитата — должна быть отброшена
            {
                "date": "2001",
                "summary": "Получил орден",
                "quote": "награждён орденом Почёта в 2001",
            },
        ],
    },
    "(news.example.com)": {
        "about_subject": "yes",
        "birth_date": {"value": "", "quote": ""},
        "birth_place": {"value": "", "quote": ""},
        "citizenship": [],
        "positions": [],
        "relations": [],
        "companies": [],
        "adverse": [
            {
                "category": "corruption",
                "summary": "Возбуждено уголовное дело о получении взятки",
                "date": "2022",
                "severity": "high",
                "quote": (
                    "против министра Петра Иванова возбуждено уголовное дело о получении взятки"
                ),
            }
        ],
        "legal": [
            {
                "kind": "criminal_case",
                "summary": "Уголовное дело о получении взятки в особо крупном размере",
                "jurisdiction": "BY",
                "status": "возбуждено",
                "date": "2022",
                "quote": "возбуждено уголовное дело о получении взятки",
            }
        ],
        "events": [],
    },
    "(minfin.gov.by)": {
        "about_subject": "yes",
        "birth_date": {"value": "", "quote": ""},
        "birth_place": {"value": "", "quote": ""},
        "citizenship": [],
        "positions": [
            {
                "title": "Министр финансов",
                "organization": "Министерство финансов Республики Беларусь",
                "country": "BY",
                "start": "2019",
                "end": "",
                "current": "yes",
                "category": "state_body",
                "quote": "назначен министром финансов Республики Беларусь указом Президента",
            }
        ],
        "relations": [],
        "companies": [],
        "adverse": [],
        "legal": [],
        "events": [],
    },
}


def _hit(url: str, title: str, content: str, engine: str = "brave") -> dict[str, Any]:
    return {"url": url, "title": title, "content": content, "engines": [engine], "score": 1.0}


SEARCH_RESULTS: list[dict[str, Any]] = [
    _hit(
        WIKI_URL,
        "Иванов, Пётр Сергеевич — Википедия",
        "Пётр Сергеевич Иванов — белорусский государственный деятель, министр финансов.",
    ),
    _hit(GOV_URL, "Министр финансов — Иванов Пётр Сергеевич", "Иванов Пётр Сергеевич, министр."),
    _hit(
        NEWS_URL,
        "Против Петра Иванова возбуждено дело",
        "В 2022 году против министра Петра Иванова возбуждено уголовное дело.",
        "bing news",
    ),
    _hit("https://weather.example.com/minsk", "Погода в Минске", "Солнечно, без осадков."),
    _hit("https://www.facebook.com/ivanov", "Пётр Иванов | Facebook", "Пётр Иванов — профиль."),
]


async def _allow_all(url: str) -> None:
    return None


def mock_web(router: respx.MockRouter, *, searx_down: bool = False) -> None:
    """SearXNG, robots.txt и страницы источников."""
    if searx_down:
        router.get(f"{SEARX}/search").mock(side_effect=httpx.ConnectError("down"))
    else:
        router.get(f"{SEARX}/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": SEARCH_RESULTS,
                    "unresponsive_engines": [["duckduckgo", "CAPTCHA"]],
                },
            )
        )
    router.get(url__regex=r".*/robots\.txt$").mock(return_value=httpx.Response(404))
    for url, html in PAGES.items():
        router.get(url).mock(
            return_value=httpx.Response(
                200, html=html, headers={"content-type": "text/html; charset=utf-8"}
            )
        )


async def build_sample(
    settings: Settings,
    *,
    llm: FakeLLM | None = None,
    screener: FakeScreener | None = None,
    searx_down: bool = False,
) -> Portrait:
    fake_llm = llm or FakeLLM(LLM_ANSWERS)
    fake_screener = screener or FakeScreener(
        {"Иванов Пётр Сергеевич": [match("PETR SERGEEVICH IVANOV", dob_match=True)]}
    )
    # Тестовые домены не резолвятся: проверку публичности адреса проверяют отдельные тесты
    with (
        respx.mock(assert_all_called=False) as router,
        patch("ipdl.fetch.fetcher.assert_public_url", _allow_all),
    ):
        mock_web(router, searx_down=searx_down)
        searx = SearxngClient(settings.search)
        fetcher = Fetcher(settings.fetch)
        try:
            deps = Deps(
                settings=settings,
                plan=load_plan(settings.search.queries_file),
                model=load_risk_model(settings.methodology_file),
                jurisdictions=load_jurisdictions(settings.jurisdictions_file),
                searxng=searx,
                fetcher=fetcher,
                extractor=FactExtractor(fake_llm),
                sanctions=fake_screener,
            )
            return await build_portrait(SUBJECT, deps)
        finally:
            await searx.aclose()
            await fetcher.aclose()
