"""Загрузка официальных санкционных списков в PostgreSQL и скрининг имён по ним.

Скрининг двухступенчатый: триграммный индекс (pg_trgm) по «скелетам» имён быстро отбирает
кандидатов, затем :func:`ipdl.names.match.similarity` считает точное сходство токенов.
Совпадение — всегда «возможное»: решение принимает аналитик (дата рождения, гражданство).
"""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import yaml
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ipdl.analysis.model import SanctionsListStatus, SanctionsMatch
from ipdl.config.settings import SanctionsSettings
from ipdl.db.models import SanctionsEntryRow, SanctionsList, SanctionsName
from ipdl.db.session import Database
from ipdl.logs import get_logger
from ipdl.names.match import entity_similarity, entity_tokens, fold, similarity, tokens
from ipdl.sanctions.parsers import SanctionsEntry, parse, published_at

log = get_logger(__name__)

_INSERT_BATCH = 2000
# Порог триграммного предотбора: заведомо ниже итогового порога сходства токенов
_TRGM_THRESHOLD = 0.3
_TRGM_CANDIDATES = 300


class SanctionsSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short: str
    url: str
    format: str
    entry_url: str | None = None


def load_sources(path: Path) -> list[SanctionsSource]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [SanctionsSource.model_validate(item) for item in data.get("lists", [])]


@dataclass(slots=True)
class UpdateResult:
    list_id: str
    status: str  # updated | unchanged | error
    entries: int = 0
    error: str | None = None


class SanctionsDownloadError(RuntimeError):
    pass


class SanctionsUpdater:
    def __init__(
        self,
        db: Database,
        settings: SanctionsSettings,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self.sources = load_sources(settings.sources_file)
        self._http = http

    async def update_all(self, *, force: bool = False) -> list[UpdateResult]:
        # Последовательно: файлы по 20–30 МБ, параллельная загрузка не ускорит разбор
        return [await self.update(source, force=force) for source in self.sources]

    async def update(self, source: SanctionsSource, *, force: bool = False) -> UpdateResult:
        await self._ensure_list_row(source)
        with tempfile.TemporaryDirectory(prefix="ipdl-sanctions-") as tmp:
            path = Path(tmp) / f"{source.id}.xml"
            try:
                digest = await self._download(source.url, path)
                async with self.db.session() as session:
                    current = await session.get(SanctionsList, source.id)
                    unchanged = current is not None and current.sha256 == digest
                    if unchanged and not force and current is not None and current.entries > 0:
                        current.fetched_at = datetime.now(UTC)
                        current.status, current.error = "ok", None
                        log.info("sanctions_unchanged", list=source.id)
                        return UpdateResult(source.id, "unchanged", current.entries)
                entries = await asyncio.to_thread(_parse_all, source.format, path)
                published = published_at(source.format, path)
            except Exception as exc:  # noqa: BLE001 — ошибка одного списка не валит остальные
                message = f"{type(exc).__name__}: {exc}"[:2000]
                log.warning("sanctions_update_failed", list=source.id, error=message)
                async with self.db.session() as session:
                    await session.execute(
                        update(SanctionsList)
                        .where(SanctionsList.id == source.id)
                        .values(status="error", error=message)
                    )
                return UpdateResult(source.id, "error", error=message)

        count = await self._replace_entries(source, entries, digest, published)
        log.info("sanctions_updated", list=source.id, entries=count)
        return UpdateResult(source.id, "updated", count)

    async def _ensure_list_row(self, source: SanctionsSource) -> None:
        async with self.db.session() as session:
            row = await session.get(SanctionsList, source.id)
            if row is None:
                session.add(
                    SanctionsList(
                        id=source.id, name=source.name, url=source.url, format=source.format
                    )
                )
            else:
                row.name, row.url, row.format = source.name, source.url, source.format

    async def _download(self, url: str, path: Path) -> str:
        digest = hashlib.sha256()
        size = 0
        client = self._http or httpx.AsyncClient(
            timeout=httpx.Timeout(self.settings.timeout_s, connect=20),
            follow_redirects=True,
            headers={"User-Agent": "IPDL-Sanctions/0.1"},
        )
        try:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with path.open("wb") as out:
                    async for chunk in response.aiter_bytes(1 << 16):
                        size += len(chunk)
                        if size > self.settings.max_bytes:
                            raise SanctionsDownloadError(
                                f"файл больше {self.settings.max_bytes} байт"
                            )
                        digest.update(chunk)
                        out.write(chunk)
        finally:
            if self._http is None:
                await client.aclose()
        if size == 0:
            raise SanctionsDownloadError("пустой ответ")
        return digest.hexdigest()

    async def _replace_entries(
        self,
        source: SanctionsSource,
        entries: list[SanctionsEntry],
        digest: str,
        published: str | None,
    ) -> int:
        async with self.db.session() as session:
            await session.execute(
                delete(SanctionsEntryRow).where(SanctionsEntryRow.list_id == source.id)
            )
            for start in range(0, len(entries), _INSERT_BATCH):
                batch = entries[start : start + _INSERT_BATCH]
                ids = (
                    await session.scalars(
                        insert(SanctionsEntryRow).returning(
                            SanctionsEntryRow.id, sort_by_parameter_order=True
                        ),
                        [_entry_row(source.id, e) for e in batch],
                    )
                ).all()
                names = [
                    {"entry_id": entry_id, "name": name[:1000], "folded": fold(name)[:1000]}
                    for entry_id, entry in zip(ids, batch, strict=True)
                    for name in entry.names
                ]
                if names:
                    await session.execute(insert(SanctionsName), names)
            await session.execute(
                update(SanctionsList)
                .where(SanctionsList.id == source.id)
                .values(
                    sha256=digest,
                    entries=len(entries),
                    fetched_at=datetime.now(UTC),
                    published_at=_to_date(published),
                    status="ok",
                    error=None,
                )
            )
        return len(entries)


def _parse_all(fmt: str, path: Path) -> list[SanctionsEntry]:
    return [e for e in parse(fmt, path) if e.primary_name and e.ref]


def _entry_row(list_id: str, entry: SanctionsEntry) -> dict[str, object]:
    return {
        "list_id": list_id,
        "ref": entry.ref[:64],
        "entity_type": entry.entity_type,
        "primary_name": entry.primary_name,
        "birth_dates": entry.birth_dates,
        "nationalities": entry.nationalities,
        "programs": entry.programs,
        "listed_on": entry.listed_on,
        "remarks": (entry.remarks or "")[:4000] or None,
    }


def _to_date(value: str | None) -> date | None:
    if not value or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------- скрининг


def dob_compatible(query: date | None, listed: Sequence[str]) -> bool | None:
    """Совместима ли дата рождения с датами из списка (``1987``, ``1987-11``, ``1987-11-13``)."""
    if query is None or not listed:
        return None
    iso = query.isoformat()
    return any(iso.startswith(value) for value in listed)


async def list_statuses(session: AsyncSession) -> list[SanctionsListStatus]:
    rows = (await session.scalars(select(SanctionsList).order_by(SanctionsList.id))).all()
    return [
        SanctionsListStatus(
            id=row.id,
            name=row.name,
            published_at=(
                datetime.combine(row.published_at, datetime.min.time(), tzinfo=UTC)
                if row.published_at
                else None
            ),
            fetched_at=row.fetched_at,
            entries=row.entries,
        )
        for row in rows
    ]


async def screen(
    session: AsyncSession,
    names: Sequence[str],
    *,
    birth_date: date | None = None,
    entity_types: Sequence[str] = ("person",),
    threshold: float = 88,
    limit: int = 20,
    sources: Sequence[SanctionsSource] = (),
) -> list[SanctionsMatch]:
    """Найти возможные совпадения имён (любой вариант написания) в загруженных списках."""
    entry_urls = {s.id: s.entry_url for s in sources}
    best: dict[tuple[str, str], SanctionsMatch] = {}
    await session.execute(
        text("SELECT set_config('pg_trgm.similarity_threshold', :v, true)"),
        {"v": str(_TRGM_THRESHOLD)},
    )
    entities = "person" not in entity_types
    for raw in dict.fromkeys(n.strip() for n in names if n and n.strip()):
        query_folded = fold(raw)
        query_tokens = entity_tokens(raw) if entities else tokens(raw)
        if len(query_folded) < 3 or not query_tokens:
            continue
        stmt = (
            select(SanctionsName.name, SanctionsEntryRow, SanctionsList.name)
            .join(SanctionsEntryRow, SanctionsEntryRow.id == SanctionsName.entry_id)
            .join(SanctionsList, SanctionsList.id == SanctionsEntryRow.list_id)
            .where(SanctionsName.folded.op("%")(query_folded))
            .where(SanctionsEntryRow.entity_type.in_(list(entity_types)))
            .order_by(text("similarity(sanctions_names.folded, :q) DESC"))
            .limit(_TRGM_CANDIDATES)
        )
        rows = (await session.execute(stmt, {"q": query_folded})).all()
        for matched_name, entry, list_name in rows:
            score = (
                entity_similarity(query_tokens, entity_tokens(matched_name))
                if entities
                else similarity(query_tokens, tokens(matched_name))
            )
            if score < threshold:
                continue
            key = (entry.list_id, entry.ref)
            if key in best and best[key].score >= score:
                continue
            url_template = entry_urls.get(entry.list_id)
            best[key] = SanctionsMatch(
                entity_type=entry.entity_type,
                list_id=entry.list_id,
                list_name=list_name,
                entry_ref=entry.ref,
                matched_name=matched_name,
                primary_name=entry.primary_name,
                score=score,
                birth_dates=list(entry.birth_dates),
                nationalities=list(entry.nationalities),
                programs=list(entry.programs),
                listed_on=entry.listed_on,
                url=url_template.replace("{ref}", entry.ref) if url_template else None,
                dob_match=dob_compatible(birth_date, entry.birth_dates),
            )
    ranked = sorted(
        best.values(),
        key=lambda m: (m.dob_match is not False, m.dob_match is True, m.score),
        reverse=True,
    )
    return ranked[:limit]


class DbScreener:
    """Скрининг по спискам в PostgreSQL — реализация ``pipeline.SanctionsScreener``."""

    def __init__(self, db: Database, settings: SanctionsSettings) -> None:
        self.db = db
        self.settings = settings
        self.sources = load_sources(settings.sources_file)

    async def screen(
        self, names: Sequence[str], *, birth_date: date | None, entity_types: Sequence[str]
    ) -> list[SanctionsMatch]:
        async with self.db.session() as session:
            return await screen(
                session,
                names,
                birth_date=birth_date,
                entity_types=entity_types,
                threshold=self.settings.match_threshold,
                limit=self.settings.max_matches,
                sources=self.sources,
            )

    async def lists(self) -> list[SanctionsListStatus]:
        async with self.db.session() as session:
            return [s for s in await list_statuses(session) if s.entries > 0]
