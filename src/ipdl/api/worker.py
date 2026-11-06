"""Воркер arq: ``ipdl worker`` (или ``arq ipdl.api.worker.WorkerSettings``).

* ``build_portrait`` — построение версии портрета (поиск, загрузка, санкции, LLM, оценка);
* ``update_sanctions`` — загрузка официальных санкционных списков (ежедневно и по запросу);
* при старте зависшие задачи (воркер был остановлен посреди работы) помечаются ошибкой.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

from arq import cron, func
from arq.connections import RedisSettings
from sqlalchemy import select, update

from ipdl.analysis.methodology import load_jurisdictions, load_risk_model
from ipdl.analysis.model import Subject
from ipdl.analysis.pipeline import Deps, Stage, build_portrait
from ipdl.api.jobs import BUILD_PORTRAIT, UPDATE_SANCTIONS
from ipdl.api.metrics import (
    PORTRAIT_DURATION,
    PORTRAITS_IN_PROGRESS,
    PORTRAITS_TOTAL,
    SANCTIONS_UPDATES,
)
from ipdl.api.registry import effective_portrait, refresh_person
from ipdl.api.state import AppState
from ipdl.auth.service import purge_expired_sessions
from ipdl.config.settings import Settings, get_settings
from ipdl.db.models import AuditEvent, JobStatus, Person, SanctionsList
from ipdl.db.models import Portrait as PortraitRow
from ipdl.db.session import Database
from ipdl.fetch.fetcher import Fetcher
from ipdl.llm.client import LLMClient, create_llm_client
from ipdl.llm.extract import FactExtractor
from ipdl.logs import configure_logging, get_logger
from ipdl.sanctions.service import DbScreener, SanctionsUpdater
from ipdl.search.collect import load_plan
from ipdl.search.searxng import SearxngClient

log = get_logger(__name__)

_PROGRESS_STEP = 2  # не писать в БД чаще, чем раз в 2 % прогресса


class _NoQueue:
    """Воркеру очередь не нужна, но AppState её ожидает."""

    async def enqueue_portrait(self, portrait_id: uuid.UUID) -> str:
        raise NotImplementedError

    async def enqueue_sanctions_update(self, *, force: bool = False) -> str:
        raise NotImplementedError

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log)
    db = Database(settings.db)
    llm: LLMClient | None = create_llm_client(settings.llm) if settings.llm.enabled else None
    searxng = SearxngClient(settings.search)
    fetcher = Fetcher(settings.fetch)
    ctx.update(
        settings=settings,
        db=db,
        llm=llm,
        searxng=searxng,
        fetcher=fetcher,
        state=AppState(settings=settings, db=db, queue=_NoQueue()),
        deps=Deps(
            settings=settings,
            plan=load_plan(settings.search.queries_file),
            model=load_risk_model(settings.methodology_file),
            jurisdictions=load_jurisdictions(settings.jurisdictions_file),
            searxng=searxng,
            fetcher=fetcher,
            extractor=FactExtractor(llm) if llm is not None else None,
            sanctions=DbScreener(db, settings.sanctions),
        ),
    )
    await _recover_stale(db, settings)
    await _requeue_waiting(db, ctx.get("redis"))
    log.info("worker_started", concurrency=settings.jobs.max_concurrency, llm=settings.llm.model)


async def shutdown(ctx: dict[str, Any]) -> None:
    if ctx.get("llm") is not None:
        await ctx["llm"].aclose()
    await ctx["searxng"].aclose()
    await ctx["fetcher"].aclose()
    await ctx["db"].dispose()


async def _recover_stale(db: Database, settings: Settings) -> None:
    """Задачи «в работе» дольше таймаута — воркер был остановлен; пометить ошибкой."""
    deadline = datetime.now(UTC) - timedelta(seconds=settings.jobs.timeout_s + 60)
    async with db.session() as session:
        result = await session.execute(
            update(PortraitRow)
            .where(
                PortraitRow.status == JobStatus.RUNNING,
                PortraitRow.started_at < deadline,
            )
            .values(
                status=JobStatus.FAILED,
                error="Построение прервано (перезапуск воркера) — запустите повторно",
                finished_at=datetime.now(UTC),
            )
        )
    count = int(getattr(result, "rowcount", 0) or 0)
    if count:
        log.warning("stale_portraits_failed", count=count)


async def _requeue_waiting(db: Database, redis: Any) -> None:
    """Redis не хранит очередь на диске: после его перезапуска ожидающие задачи ставятся заново.

    Идентификатор задачи = id портрета, поэтому уже стоящая в очереди задача не дублируется.
    """
    if redis is None:
        return
    async with db.session() as session:
        waiting = (
            await session.scalars(
                select(PortraitRow.id).where(PortraitRow.status == JobStatus.QUEUED)
            )
        ).all()
    for portrait_id in waiting:
        await redis.enqueue_job(BUILD_PORTRAIT, str(portrait_id), _job_id=f"portrait:{portrait_id}")
    if waiting:
        log.info("portraits_requeued", count=len(waiting))


async def build_portrait_job(ctx: dict[str, Any], portrait_id: str) -> None:
    db: Database = ctx["db"]
    settings: Settings = ctx["settings"]
    pid = uuid.UUID(portrait_id)
    async with db.session() as session:
        row = await session.get(PortraitRow, pid)
        if row is None or row.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            log.info("portrait_job_skipped", portrait=portrait_id)
            return
        row.status, row.started_at, row.stage, row.progress = (
            JobStatus.RUNNING,
            datetime.now(UTC),
            Stage.SEARCH.value,
            0,
        )
        subject = Subject.model_validate(row.params)

    last_stage, last_percent = Stage.SEARCH, 0

    async def progress(stage: Stage, percent: int) -> None:
        nonlocal last_stage, last_percent
        if stage is last_stage and percent - last_percent < _PROGRESS_STEP:
            return
        last_stage, last_percent = stage, percent
        async with db.session() as session:
            await session.execute(
                update(PortraitRow)
                .where(PortraitRow.id == pid)
                .values(stage=stage.value, progress=min(percent, 99))
            )

    started = time.perf_counter()
    PORTRAITS_IN_PROGRESS.inc()
    try:
        portrait = await asyncio.wait_for(
            build_portrait(subject, ctx["deps"], progress), timeout=settings.jobs.timeout_s
        )
    except Exception as exc:
        message = (
            "Превышено время построения портрета"
            if isinstance(exc, TimeoutError)
            else f"Ошибка построения портрета: {type(exc).__name__}"
        )
        log.exception("portrait_failed", portrait=portrait_id)
        async with db.session() as session:
            await session.execute(
                update(PortraitRow)
                .where(PortraitRow.id == pid)
                .values(status=JobStatus.FAILED, error=message, finished_at=datetime.now(UTC))
            )
        PORTRAITS_TOTAL.labels("failed").inc()
        return
    finally:
        PORTRAITS_IN_PROGRESS.dec()

    async with db.session() as session:
        row = await session.get(PortraitRow, pid)
        if row is None:  # запись удалили, пока строился портрет
            return
        row.data = portrait.model_dump(mode="json")
        row.status, row.stage, row.progress = JobStatus.DONE, Stage.ASSESS.value, 100
        row.finished_at, row.error = datetime.now(UTC), None
        person = await session.get(Person, row.person_id)
        effective = effective_portrait(row, ctx["state"])
        if person is not None and effective is not None:
            refresh_person(person, row, effective)
        session.add(
            AuditEvent(
                action="portrait_built",
                object_type="portrait",
                object_id=str(pid),
                details={
                    "version": row.version,
                    "score": portrait.risk.score,
                    "pep": portrait.pep.category.value,
                    "sources": portrait.stats.sources,
                    "seconds": portrait.stats.duration_s,
                },
            )
        )
    PORTRAITS_TOTAL.labels("done").inc()
    PORTRAIT_DURATION.observe(time.perf_counter() - started)


async def update_sanctions_job(ctx: dict[str, Any], force: bool = False) -> dict[str, int]:
    updater = SanctionsUpdater(ctx["db"], ctx["settings"].sanctions)
    results = await updater.update_all(force=force)
    async with ctx["db"].session() as session:
        session.add(
            AuditEvent(
                action="sanctions_updated",
                details={r.list_id: {"status": r.status, "entries": r.entries} for r in results},
            )
        )
    for result in results:
        SANCTIONS_UPDATES.labels(result.list_id, result.status).inc()
    return {r.list_id: r.entries for r in results}


async def scheduled_sanctions(ctx: dict[str, Any]) -> None:
    await update_sanctions_job(ctx)


async def purge_sessions(ctx: dict[str, Any]) -> None:
    async with ctx["db"].session() as session:
        removed = await purge_expired_sessions(session)
    log.info("sessions_purged", removed=removed)


async def startup_sanctions_if_empty(ctx: dict[str, Any]) -> None:
    """Первый запуск: списки ещё не загружены — загрузить, не дожидаясь ночного обновления."""
    async with ctx["db"].session() as session:
        loaded = (
            await session.scalars(select(SanctionsList).where(SanctionsList.entries > 0))
        ).all()
    if not loaded:
        await update_sanctions_job(ctx)


async def _startup(ctx: dict[str, Any]) -> None:
    await startup(ctx)
    # Ссылка на задачу хранится в ctx, иначе сборщик мусора может её отменить
    ctx["bootstrap"] = asyncio.create_task(startup_sanctions_if_empty(ctx))


_settings = get_settings()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [
        func(
            build_portrait_job,
            name=BUILD_PORTRAIT,
            max_tries=1,  # повтор длинной задачи — только по решению аналитика
            timeout=int(_settings.jobs.timeout_s) + 60,
            keep_result=0,  # результат хранится в PostgreSQL
        ),
        func(
            update_sanctions_job,
            name=UPDATE_SANCTIONS,
            max_tries=2,
            timeout=int(_settings.sanctions.timeout_s) * 8 + 300,
            keep_result=0,
        ),
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(scheduled_sanctions, hour={_settings.sanctions.update_hour_utc}, minute={15}),
        cron(purge_sessions, hour={4}, minute={30}),
    ]
    on_startup = _startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(_settings.jobs.redis_url)
    queue_name = _settings.jobs.queue_name
    max_jobs = _settings.jobs.max_concurrency
    job_timeout = int(_settings.jobs.timeout_s) + 60
    health_check_interval = 30
