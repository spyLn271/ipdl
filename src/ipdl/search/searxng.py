"""Клиент SearXNG (JSON API ``/search?format=json``).

SearXNG — метапоиск: один запрос опрашивает несколько поисковиков (Brave, Yandex, Bing News…)
и возвращает объединённую выдачу. Экземпляр свой (docker compose), без лимитера, наружу не
публикуется. Поисковики, недоступные с сервера (капча, блокировка), SearXNG сам помечает в
``unresponsive_engines`` — это пишем в лог и в предупреждения портрета.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential

from ipdl.config.settings import SearchSettings
from ipdl.logs import get_logger

log = get_logger(__name__)


class SearchError(RuntimeError):
    """SearXNG недоступен или вернул ошибку."""


@dataclass(slots=True)
class SearchHit:
    url: str
    title: str
    content: str
    engines: list[str]
    category: str
    score: float
    published: date | None = None


@dataclass(slots=True)
class SearchPage:
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    unresponsive: list[str] = field(default_factory=list)


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500


def _published(raw: object) -> date | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


class SearxngClient:
    def __init__(self, settings: SearchSettings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http = http or httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=httpx.Timeout(settings.timeout_s, connect=5.0),
            headers={"Accept": "application/json"},
        )
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def search(
        self, query: str, *, category: str = "general", language: str = "all", pageno: int = 1
    ) -> SearchPage:
        params = {
            "q": query,
            "format": "json",
            "categories": category,
            "language": language,
            "pageno": str(pageno),
            "safesearch": "0",
        }
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=0.5, max=4),
                retry=retry_if_exception(_retryable),
                reraise=True,
            ):
                with attempt:
                    response = await self._http.get("/search", params=params)
                    response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SearchError(f"SearXNG ({self.settings.base_url}): {exc}") from exc

        payload = response.json()
        page = SearchPage(
            query=query,
            unresponsive=[str(item[0]) for item in payload.get("unresponsive_engines", [])],
        )
        for item in payload.get("results", [])[: self.settings.max_results_per_query]:
            url = str(item.get("url") or "")
            if not url.startswith(("http://", "https://")):
                continue
            page.hits.append(
                SearchHit(
                    url=url,
                    title=str(item.get("title") or "").strip(),
                    content=str(item.get("content") or "").strip(),
                    engines=[str(e) for e in item.get("engines", [])],
                    category=str(item.get("category") or category),
                    score=float(item.get("score") or 0),
                    published=_published(item.get("publishedDate")),
                )
            )
        if page.unresponsive:
            log.info("searxng_unresponsive", query=query, engines=page.unresponsive)
        return page

    async def health(self) -> bool:
        try:
            response = await self._http.get("/healthz", timeout=5)
        except httpx.HTTPError:
            return False
        return response.is_success
