from __future__ import annotations

import httpx
import pytest
import respx

from ipdl.analysis.model import SourceKind, Subject
from ipdl.config.settings import FetchSettings, SearchSettings
from ipdl.fetch.extract import clean_paragraph, extract_text, relevant_passages
from ipdl.fetch.fetcher import (
    BlockedURLError,
    FetchedDocument,
    Fetcher,
    FetchError,
    assert_public_url,
)
from ipdl.search.collect import (
    QueryPlan,
    QueryTemplate,
    build_queries,
    classify_domain,
    collect,
    domain_of,
    mentions,
    name_forms,
    normalize_url,
)
from ipdl.search.searxng import SearchError, SearxngClient

# ---------------------------------------------------------------- имена и запросы


def test_name_forms_drop_patronymic_and_reorder() -> None:
    forms = name_forms(Subject(full_name="Турлов Тимур Русланович"))
    assert forms.short == "Тимур Турлов"
    assert forms.latin == "Timur Turlov"
    assert ["timur", "тимур"] in forms.stems


def test_name_forms_keep_given_latin() -> None:
    forms = name_forms(Subject(full_name="Иванов Пётр", latin_name="Pyotr Ivanov"))
    assert forms.latin == "Pyotr Ivanov"
    assert forms.short == "Иванов Пётр"


def test_mentions_ignore_stress_and_case() -> None:
    forms = name_forms(Subject(full_name="Турлов Тимур Русланович"))
    assert mentions("Тиму́р Русла́нович Турло́в (род. 1987)", forms) == 2
    assert mentions("Компания Турлова выросла", forms) == 1
    assert mentions("Ничего о нём", forms) == 0


def test_build_queries_skip_missing_values() -> None:
    plan = QueryPlan(
        queries=[
            QueryTemplate(topic="identity", q="{name}"),
            QueryTemplate(topic="identity", q="{short} {context}"),
            QueryTemplate(topic="identity", q="{name}"),  # дубль
        ]
    )
    subject = Subject(full_name="Иванов Пётр Сергеевич")
    queries = build_queries(plan, subject, name_forms(subject))
    assert [q.q for q in queries] == ["Иванов Пётр Сергеевич"]


def test_url_helpers() -> None:
    assert (
        normalize_url("HTTPS://WWW.Example.com/a/?utm_source=x&id=5#frag")
        == "https://www.example.com/a?id=5"
    )
    assert domain_of("https://www.example.com/x") == "example.com"


@pytest.mark.parametrize(
    ("domain", "category", "kind"),
    [
        ("minfin.gov.by", "general", SourceKind.OFFICIAL),
        ("treasury.gov", "general", SourceKind.OFFICIAL),
        ("akorda.kz", "general", SourceKind.OFFICIAL),
        ("ru.wikipedia.org", "general", SourceKind.REFERENCE),
        ("kompra.kz", "general", SourceKind.CORPORATE),
        ("reuters.com", "general", SourceKind.MEDIA),
        ("someblog.kz", "news", SourceKind.MEDIA),
        ("someblog.kz", "general", SourceKind.OTHER),
    ],
)
def test_classify_domain(domain: str, category: str, kind: SourceKind) -> None:
    assert classify_domain(domain, category) is kind


SEARX = "http://searxng.test"


async def test_collect_ranks_and_filters() -> None:
    settings = SearchSettings(base_url=SEARX)
    results = [
        {
            "url": "https://news.example.com/a",
            "title": "Пётр Иванов арестован",
            "content": "...",
            "engines": ["bing news"],
            "category": "news",
        },
        {
            "url": "https://ru.wikipedia.org/wiki/X",
            "title": "Иванов, Пётр Сергеевич",
            "content": "Пётр Иванов — министр",
            "engines": ["brave", "yandex"],
        },
        {
            "url": "https://spam.example.com",
            "title": "Купить окна",
            "content": "дёшево",
            "engines": ["brave"],
        },
        {
            "url": "https://www.facebook.com/x",
            "title": "Пётр Иванов",
            "content": "Пётр Иванов",
            "engines": ["brave"],
        },
        {"url": "ftp://bad", "title": "Пётр Иванов", "content": "", "engines": []},
    ]
    plan = QueryPlan(
        queries=[
            QueryTemplate(topic="identity", q="{name}"),
            QueryTemplate(topic="news", category="news", q="{short}"),
        ]
    )
    progress: list[tuple[int, int]] = []

    async def on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    with respx.mock() as router:
        router.get(f"{SEARX}/search").mock(
            return_value=httpx.Response(
                200, json={"results": results, "unresponsive_engines": [["google", "CAPTCHA"]]}
            )
        )
        client = SearxngClient(settings)
        collection = await collect(
            client,
            plan,
            Subject(full_name="Иванов Пётр Сергеевич"),
            max_concurrency=2,
            max_sources=10,
            on_progress=on_progress,
        )
        await client.aclose()
    urls = [c.url for c in collection.candidates]
    assert urls[0] == "https://ru.wikipedia.org/wiki/X"
    assert "https://spam.example.com/" not in urls
    assert not any("facebook" in u for u in urls)
    assert collection.queries == 2
    assert collection.unresponsive == {"google": 2}
    news = next(c for c in collection.candidates if c.domain == "news.example.com")
    assert news.kind is SourceKind.MEDIA
    assert progress[-1] == (2, 2)


async def test_searxng_errors_are_wrapped() -> None:
    with respx.mock() as router:
        router.get(f"{SEARX}/search").mock(return_value=httpx.Response(503))
        client = SearxngClient(SearchSettings(base_url=SEARX))
        with pytest.raises(SearchError):
            await client.search("x")
        await client.aclose()


async def test_searxng_health() -> None:
    with respx.mock() as router:
        router.get(f"{SEARX}/healthz").mock(return_value=httpx.Response(200))
        client = SearxngClient(SearchSettings(base_url=SEARX))
        assert await client.health()
        await client.aclose()


# ---------------------------------------------------------------- SSRF


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "https://8.8.8.8:8443/",
        "file:///etc/passwd",
        "gopher://8.8.8.8/",
        "http://user:pass@8.8.8.8/",
    ],
)
async def test_private_and_odd_urls_are_blocked(url: str) -> None:
    with pytest.raises(BlockedURLError):
        await assert_public_url(url)


async def test_public_ip_is_allowed() -> None:
    await assert_public_url("https://8.8.8.8/")


async def test_redirect_to_private_address_is_blocked() -> None:
    fetcher = Fetcher(FetchSettings(respect_robots_txt=False))
    with respx.mock() as router:
        router.get("https://8.8.8.8/start").mock(
            return_value=httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})
        )
        with pytest.raises(BlockedURLError):
            await fetcher.fetch("https://8.8.8.8/start")
    await fetcher.aclose()


async def test_robots_txt_is_respected() -> None:
    fetcher = Fetcher(FetchSettings())
    with respx.mock() as router:
        router.get("https://8.8.4.4/robots.txt").mock(
            return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        )
        router.get("https://8.8.4.4/public").mock(
            return_value=httpx.Response(
                200, html="<p>ok</p>", headers={"content-type": "text/html"}
            )
        )
        with pytest.raises(BlockedURLError):
            await fetcher.fetch("https://8.8.4.4/private/page")
        document = await fetcher.fetch("https://8.8.4.4/public")
    assert document.body == b"<p>ok</p>"
    await fetcher.aclose()


async def test_fetch_limits_size_and_types() -> None:
    fetcher = Fetcher(FetchSettings(respect_robots_txt=False, max_bytes=10_000))
    with respx.mock() as router:
        router.get("https://1.1.1.1/big").mock(
            return_value=httpx.Response(
                200, content=b"x" * 50_000, headers={"content-type": "text/html"}
            )
        )
        router.get("https://1.1.1.1/image").mock(
            return_value=httpx.Response(
                200, content=b"GIF89a", headers={"content-type": "image/gif"}
            )
        )
        router.get("https://1.1.1.1/missing").mock(return_value=httpx.Response(404))
        big = await fetcher.fetch("https://1.1.1.1/big")
        assert len(big.body) == 10_000
        with pytest.raises(FetchError):
            await fetcher.fetch("https://1.1.1.1/image")
        with pytest.raises(FetchError):
            await fetcher.fetch("https://1.1.1.1/missing")
    await fetcher.aclose()


# ---------------------------------------------------------------- извлечение текста


def test_clean_paragraph() -> None:
    assert clean_paragraph("Тиму́р  Турло́в[1][23] [править | править код]") == "Тимур Турлов"


def test_relevant_passages_keep_mentions_and_continuations() -> None:
    forms = name_forms(Subject(full_name="Иванов Пётр Сергеевич"))
    lines = [
        "| Таблица | без | смысла |",
        "Реклама: купите окна недорого прямо сейчас у нас.",
        "Пётр Иванов (род. 1970) — министр финансов Беларуси с 2019 года.",
        "Окончил экономический университет в 1992 году с отличием.",
        "Совершенно посторонний абзац о погоде в городе и окрестностях.",
        "Через год Иванов возглавил комиссию по бюджету правительства.",
    ]
    text = "\n".join(lines)
    passages = relevant_passages(text, forms, max_chars=2000)
    assert "министр финансов" in passages
    assert "Окончил экономический" in passages
    assert "Реклама" not in passages
    assert "Таблица" not in passages
    assert (
        relevant_passages(text, forms, max_chars=300).endswith("…")
        or len(relevant_passages(text, forms, max_chars=300)) <= 300
    )


def test_extract_html_and_text() -> None:
    html = (
        "<html><head><title>Профиль</title></head><body><nav>Меню Главная Контакты</nav>"
        "<article><h1>Иванов</h1>"
        "<p>Пётр Иванов — министр финансов Республики Беларусь с 2019 года. "
        "Ранее он работал заместителем министра экономики и возглавлял департамент бюджета.</p>"
        "<p>В 2022 году против Петра Иванова возбуждено уголовное дело о получении взятки.</p>"
        "</article></body></html>"
    )
    doc = FetchedDocument("https://x", "https://x", "text/html", html.encode())
    extracted = extract_text(doc)
    assert extracted is not None
    assert "министр финансов" in extracted.text
    plain = extract_text(FetchedDocument("https://x", "https://x", "text/plain", "привет".encode()))
    assert plain is not None
    assert plain.text == "привет"
    assert (
        extract_text(FetchedDocument("https://x", "https://x", "application/pdf", b"not a pdf"))
        is None
    )
