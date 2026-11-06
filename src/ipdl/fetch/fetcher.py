"""Загрузка найденных страниц с защитой от SSRF.

Ссылки приходят из поисковой выдачи — то есть из интернета, поэтому:

* только ``http``/``https`` и стандартные порты;
* хост разрешается в IP заранее, запрещены приватные, loopback, link-local и прочие
  неглобальные адреса (внутренние сервисы docker compose, метаданные облака);
* редиректы обрабатываются вручную, каждый адрес проверяется заново;
* ответ читается потоком и обрывается на ``max_bytes``;
* ``robots.txt`` соблюдается (настройка ``fetch.respect_robots_txt``).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ipdl.config.settings import FetchSettings
from ipdl.logs import get_logger

log = get_logger(__name__)

_ALLOWED_PORTS = frozenset({80, 443})
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_PDF_TYPES = ("application/pdf",)
_TEXT_TYPES = ("text/plain",)


class FetchError(RuntimeError):
    pass


class BlockedURLError(FetchError):
    """Адрес запрещён политикой безопасности (не публичный IP, порт, схема, robots.txt)."""


@dataclass(slots=True)
class FetchedDocument:
    url: str
    final_url: str
    content_type: str
    body: bytes


def _port(scheme: str, port: int | None) -> int:
    return port if port is not None else (443 if scheme == "https" else 80)


async def assert_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise BlockedURLError(f"схема {parts.scheme!r} запрещена")
    if not parts.hostname:
        raise BlockedURLError("нет имени хоста")
    if parts.username or parts.password:
        raise BlockedURLError("учётные данные в URL запрещены")
    port = _port(parts.scheme, parts.port)
    if port not in _ALLOWED_PORTS:
        raise BlockedURLError(f"порт {port} запрещён")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, port, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise FetchError(f"не удалось разрешить {parts.hostname}: {exc}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global or address.is_multicast:
            raise BlockedURLError(f"{parts.hostname} → {address}: адрес не публичный")


class Fetcher:
    def __init__(self, settings: FetchSettings, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._http = http or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.timeout_s, connect=6.0),
            follow_redirects=False,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
                "Accept-Language": "ru,kk;q=0.9,en;q=0.8",
            },
        )
        self._owns_http = http is None
        self._robots: dict[str, RobotFileParser | None] = {}
        self._robots_lock = asyncio.Lock()

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def fetch(self, url: str) -> FetchedDocument:
        current = url
        for _ in range(self.settings.max_redirects + 1):
            await assert_public_url(current)
            if not await self._robots_allow(current):
                raise BlockedURLError("запрещено robots.txt")
            async with self._http.stream("GET", current) as response:
                if response.status_code in _REDIRECTS:
                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(f"редирект без Location ({response.status_code})")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise FetchError(f"HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if not content_type.startswith((*_HTML_TYPES, *_PDF_TYPES, *_TEXT_TYPES)):
                    raise FetchError(f"тип {content_type or 'неизвестен'} не поддерживается")
                body = await self._read_limited(response)
                return FetchedDocument(
                    url=url, final_url=current, content_type=content_type, body=body
                )
        raise FetchError("слишком много редиректов")

    async def _read_limited(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes(1 << 15):
            size += len(chunk)
            if size > self.settings.max_bytes:
                # Начало большой страницы обычно содержит основной текст — берём его
                chunks.append(chunk[: max(0, len(chunk) - (size - self.settings.max_bytes))])
                break
            chunks.append(chunk)
        return b"".join(chunks)

    async def _robots_allow(self, url: str) -> bool:
        if not self.settings.respect_robots_txt:
            return True
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self._robots_lock:
            if origin not in self._robots:
                self._robots[origin] = await self._load_robots(origin)
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(self.settings.user_agent, url)

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        robots_url = f"{origin}/robots.txt"
        try:
            await assert_public_url(robots_url)
            response = await self._http.get(robots_url, timeout=5)
        except (httpx.HTTPError, FetchError):
            return None
        if response.status_code >= 400 or response.status_code in _REDIRECTS:
            return None  # нет robots.txt — ограничений нет
        parser = RobotFileParser()
        parser.parse(response.text[:200_000].splitlines())
        return parser
