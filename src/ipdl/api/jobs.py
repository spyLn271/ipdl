"""Очередь фоновых задач (arq + Redis): построение портретов и обновление санкционных списков."""

from __future__ import annotations

import uuid
from typing import Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from ipdl.config.settings import JobSettings

BUILD_PORTRAIT = "build_portrait"
UPDATE_SANCTIONS = "update_sanctions"


class JobQueue(Protocol):
    async def enqueue_portrait(self, portrait_id: uuid.UUID) -> str: ...

    async def enqueue_sanctions_update(self, *, force: bool = False) -> str: ...

    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


class ArqJobQueue:
    def __init__(self, pool: ArqRedis, settings: JobSettings) -> None:
        self._pool = pool
        self._settings = settings

    @classmethod
    async def connect(cls, settings: JobSettings) -> ArqJobQueue:
        pool = await create_pool(
            RedisSettings.from_dsn(settings.redis_url), default_queue_name=settings.queue_name
        )
        return cls(pool, settings)

    async def enqueue_portrait(self, portrait_id: uuid.UUID) -> str:
        # _job_id = id портрета: повторная постановка той же версии не создаёт дубль
        job = await self._pool.enqueue_job(
            BUILD_PORTRAIT, str(portrait_id), _job_id=f"portrait:{portrait_id}"
        )
        return job.job_id if job else f"portrait:{portrait_id}"

    async def enqueue_sanctions_update(self, *, force: bool = False) -> str:
        job = await self._pool.enqueue_job(UPDATE_SANCTIONS, force, _job_id="sanctions:update")
        return job.job_id if job else "sanctions:update"

    async def ping(self) -> bool:
        try:
            return bool(await self._pool.ping())
        except (OSError, ConnectionError):
            return False

    async def aclose(self) -> None:
        await self._pool.aclose()
