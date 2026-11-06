"""Сбор кандидатов в источники: запросы к SearXNG → дедупликация → ранжирование.

Ранжирование простое и объяснимое: упоминание лица в заголовке/сниппете, сколько запросов
и поисковиков вернули ссылку, тип источника (официальный > справочник > СМИ).
Ссылки, где лицо не упоминается, отбрасываются: однофамильцы и шум поисковиков.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ipdl.analysis.model import SourceKind, Subject
from ipdl.logs import get_logger
from ipdl.names.translit import has_cyrillic, transliterate
from ipdl.search.searxng import SearchError, SearchPage, SearxngClient

log = get_logger(__name__)

_PATRONYMIC = re.compile(
    r"(вич|вна|ична|инична|ьич|улы|ұлы|уулу|кызы|қызы|оглы|ogly|vich|vna|uly|kyzy)$", re.IGNORECASE
)
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|yclid$|ref$|mc_)", re.IGNORECASE)
_OFFICIAL_LABELS = frozenset({"gov", "gob", "gouv", "govt", "mil", "int"})
_OFFICIAL_DOMAINS = (
    "europa.eu",
    "un.org",
    "worldbank.org",
    "imf.org",
    "oecd.org",
    "osce.org",
    "fatf-gafi.org",
    "egov.kz",
    "akorda.kz",
    "parlam.kz",
    "zan.kz",
    "kremlin.ru",
    "government.ru",
    "duma.gov.ru",
    "president.gov.ua",
    "nsdc.gov.ua",
    "opensanctions.org",
)
_REFERENCE_DOMAINS = (
    "wikipedia.org",
    "wikidata.org",
    "ruwiki.ru",
    "britannica.com",
    "persons-info.com",
)
_CORPORATE_DOMAINS = (
    "opencorporates.com",
    "kompra.kz",
    "adata.kz",
    "rusprofile.ru",
    "list-org.com",
    "companieshouse.gov.uk",
    "find-and-update.company-information.service.gov.uk",
    "sec.gov",
)
_MEDIA_DOMAINS = (
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "nytimes.com",
    "theguardian.com",
    "bbc.com",
    "bbc.co.uk",
    "apnews.com",
    "occrp.org",
    "forbes.com",
    "forbes.ru",
    "forbes.kz",
    "rbc.ru",
    "kommersant.ru",
    "vedomosti.ru",
    "interfax.ru",
    "interfax.kz",
    "interfax.com.ua",
    "tass.ru",
    "ria.ru",
    "meduza.io",
    "novayagazeta.eu",
    "tengrinews.kz",
    "zakon.kz",
    "kapital.kz",
    "kursiv.media",
    "inbusiness.kz",
    "informburo.kz",
    "vlast.kz",
    "orda.kz",
    "khabar.kz",
    "kazinform.kz",
    "total.kz",
    "azattyq.org",
    "rferl.org",
    "currenttime.tv",
)
_SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "vk.com",
    "ok.ru",
    "youtube.com",
    "linkedin.com",
    "t.me",
)


class QueryTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    category: str = "general"
    language: str = "all"
    q: str


class QueryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: list[QueryTemplate]
    exclude_domains: list[str] = Field(default_factory=list)


def load_plan(path: Path) -> QueryPlan:
    return QueryPlan.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(slots=True)
class NameForms:
    full: str
    short: str
    latin: str | None
    stems: list[list[str]]  # для каждого токена имени — варианты основы (кириллица, латиница)


def name_forms(subject: Subject) -> NameForms:
    """Варианты имени для запросов и для проверки, что страница — об этом человеке."""
    words = subject.full_name.split()
    core = [w for w in words if not _PATRONYMIC.search(w)] or words
    if len(words) == 3 and _PATRONYMIC.search(words[2]):
        core = [words[1], words[0]]  # «Фамилия Имя Отчество» → «Имя Фамилия»
    short = " ".join(core)
    latin = subject.latin_name
    if not latin and has_cyrillic(short):
        latin = transliterate(short, "popular")
    elif not latin:
        latin = short
    latin_core = [w for w in latin.split() if not _PATRONYMIC.search(w)] or latin.split()
    stems: list[list[str]] = []
    for index, word in enumerate(core):
        variants = {_stem(word)}
        variants.add(_stem(transliterate(word, "popular")))
        variants.add(_stem(transliterate(word, "icao")))
        if index < len(latin_core) and len(core) == len(latin_core):
            variants.add(_stem(latin_core[index]))
        stems.append(sorted(v for v in variants if v))
    if len(core) != len(latin_core):
        stems.extend([[_stem(w)] for w in latin_core])
    return NameForms(full=subject.full_name, short=short, latin=latin, stems=stems)


def _stem(word: str) -> str:
    """Основа для поиска с учётом падежей: «Турлов» → «турлов», «Турлова» → «турлов»."""
    w = word.lower().replace("ё", "е").strip(".,")
    if len(w) <= 4:
        return w
    return w[:-1] if w[-1] in "аяыиеуюоaeiouy" else w


_STRESS = re.compile("[\u0300\u0301]")


def mentions(text: str, forms: NameForms) -> int:
    """Сколько токенов имени (из разных) встречается в тексте (ударения и «ё» не мешают)."""
    lowered = unicodedata.normalize("NFC", _STRESS.sub("", unicodedata.normalize("NFD", text)))
    lowered = lowered.lower().replace("ё", "е")
    return sum(1 for variants in forms.stems if any(v in lowered for v in variants))


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def domain_of(url: str) -> str:
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.")


def _matches(domain: str, suffixes: tuple[str, ...]) -> bool:
    return any(domain == s or domain.endswith("." + s) for s in suffixes)


def classify_domain(domain: str, category: str = "general") -> SourceKind:
    labels = set(domain.split("."))
    if labels & _OFFICIAL_LABELS or _matches(domain, _OFFICIAL_DOMAINS):
        return SourceKind.OFFICIAL
    if _matches(domain, _REFERENCE_DOMAINS):
        return SourceKind.REFERENCE
    if _matches(domain, _CORPORATE_DOMAINS):
        return SourceKind.CORPORATE
    if category == "news" or _matches(domain, _MEDIA_DOMAINS):
        return SourceKind.MEDIA
    return SourceKind.OTHER


_KIND_BONUS = {
    SourceKind.OFFICIAL: 0.8,
    SourceKind.REFERENCE: 0.6,
    SourceKind.CORPORATE: 0.4,
    SourceKind.MEDIA: 0.3,
    SourceKind.OTHER: 0.0,
}


@dataclass(slots=True)
class Candidate:
    url: str
    title: str
    snippet: str
    domain: str
    kind: SourceKind
    published: date | None
    engines: set[str] = field(default_factory=set)
    topics: set[str] = field(default_factory=set)
    hits: int = 0
    name_hits: int = 0
    relevance: float = 0.0


@dataclass(slots=True)
class Collection:
    candidates: list[Candidate]
    queries: int
    results: int
    unresponsive: dict[str, int]
    failed_queries: int


def build_queries(plan: QueryPlan, subject: Subject, forms: NameForms) -> list[QueryTemplate]:
    values = {
        "name": forms.full,
        "short": forms.short,
        "latin": forms.latin or "",
        "context": subject.context or "",
    }
    result: list[QueryTemplate] = []
    seen: set[tuple[str, str]] = set()
    for template in plan.queries:
        needed = set(re.findall(r"{(\w+)}", template.q))
        if any(not values.get(key) for key in needed):
            continue
        query = " ".join(template.q.format(**values).split())
        key = (query.lower(), template.category)
        if key in seen:
            continue
        seen.add(key)
        result.append(template.model_copy(update={"q": query}))
    return result


async def collect(
    client: SearxngClient,
    plan: QueryPlan,
    subject: Subject,
    *,
    max_concurrency: int,
    max_sources: int,
    stagger_s: float = 0.0,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> Collection:
    forms = name_forms(subject)
    queries = build_queries(plan, subject, forms)
    semaphore = asyncio.Semaphore(max_concurrency)
    done = 0

    async def run(index: int, template: QueryTemplate) -> tuple[QueryTemplate, SearchPage | None]:
        nonlocal done
        # Поисковики (Brave) ограничивают частоту: запросы стартуют с интервалом
        await asyncio.sleep(index * stagger_s)
        async with semaphore:
            try:
                page = await client.search(
                    template.q, category=template.category, language=template.language
                )
            except SearchError as exc:
                log.warning("search_query_failed", query=template.q, error=str(exc))
                page = None
        done += 1
        if on_progress is not None:
            await on_progress(done, len(queries))
        return template, page

    pages = await asyncio.gather(*(run(i, t) for i, t in enumerate(queries)))
    excluded = tuple(plan.exclude_domains) + _SOCIAL_DOMAINS
    by_url: dict[str, Candidate] = {}
    unresponsive: dict[str, int] = {}
    results = 0
    failed = 0
    for template, page in pages:
        if page is None:
            failed += 1
            continue
        for engine in page.unresponsive:
            unresponsive[engine] = unresponsive.get(engine, 0) + 1
        for hit in page.hits:
            results += 1
            url = normalize_url(hit.url)
            domain = domain_of(url)
            if not domain or _matches(domain, excluded):
                continue
            candidate = by_url.get(url)
            if candidate is None:
                candidate = by_url[url] = Candidate(
                    url=url,
                    title=hit.title,
                    snippet=hit.content,
                    domain=domain,
                    kind=classify_domain(domain, hit.category),
                    published=hit.published,
                )
            else:
                if len(hit.content) > len(candidate.snippet):
                    candidate.snippet = hit.content
                if candidate.kind is SourceKind.OTHER and hit.category == "news":
                    candidate.kind = SourceKind.MEDIA
            candidate.engines.update(hit.engines)
            candidate.topics.add(template.topic)
            candidate.hits += 1

    for candidate in by_url.values():
        title_hits = mentions(candidate.title, forms)
        text_hits = mentions(f"{candidate.title} {candidate.snippet}", forms)
        candidate.name_hits = text_hits
        candidate.relevance = round(_relevance(candidate, title_hits, text_hits, forms), 3)

    needed = min(2, len(forms.stems))
    ranked = sorted(
        (c for c in by_url.values() if c.name_hits >= needed),
        key=lambda c: c.relevance,
        reverse=True,
    )
    log.info(
        "search_collected",
        queries=len(queries),
        results=results,
        unique=len(by_url),
        relevant=len(ranked),
    )
    return Collection(
        candidates=ranked[:max_sources],
        queries=len(queries),
        results=results,
        unresponsive=unresponsive,
        failed_queries=failed,
    )


def _relevance(candidate: Candidate, title_hits: int, text_hits: int, forms: NameForms) -> float:
    full = len(forms.stems)
    score = 0.0
    score += 2.0 if title_hits >= min(2, full) else 0.5 * title_hits
    score += 1.0 if text_hits >= min(2, full) else 0.0
    score += 0.3 * min(candidate.hits - 1, 4)
    score += 0.2 * min(len(candidate.engines) - 1, 3)
    score += _KIND_BONUS[candidate.kind]
    if "identity" in candidate.topics:
        score += 0.4
    if candidate.topics & {"sanctions", "legal", "adverse"}:
        score += 0.3
    return score
