"""FastAPI-приложение: ``uvicorn ipdl.api.app:create_app --factory``.

API доступно только через веб-интерфейс (Next.js проксирует ``/api/v1`` с того же домена),
поэтому CORS не включается: cookie сессии работают только для своего домена.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ipdl import __version__
from ipdl.api.errors import error_body, install_error_handlers
from ipdl.api.jobs import ArqJobQueue, JobQueue
from ipdl.api.metrics import HTTP_DURATION
from ipdl.api.routes import admin, auth, exchange, meta, persons, sanctions
from ipdl.api.state import AppState
from ipdl.config.settings import Settings, get_settings
from ipdl.db.session import Database
from ipdl.logs import configure_logging, get_logger

log = get_logger(__name__)

API_PREFIX = "/api/v1"
_MAX_BODY = 256 * 1024  # JSON-запросы; файлов API не принимает
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    # В ответах API — персональные данные: не кэшировать нигде
    "Cache-Control": "no-store",
}


def create_app(
    settings: Settings | None = None,
    *,
    db: Database | None = None,
    queue: JobQueue | None = None,
) -> FastAPI:
    """Фабрика приложения. База и очередь подменяются в тестах."""
    settings = settings or get_settings()
    configure_logging(settings.log)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_db = db or Database(settings.db)
        app_queue = queue or await ArqJobQueue.connect(settings.jobs)
        state = AppState(settings=settings, db=app_db, queue=app_queue)
        # Методика и справочники проверяются при старте: ошибка в YAML — сразу, а не в отчёте
        _ = state.risk_model, state.jurisdictions, state.sanctions_sources
        app.state.ipdl = state
        log.info("api_started", version=__version__, env=settings.env.value)
        try:
            yield
        finally:
            if queue is None:
                await app_queue.aclose()
            if db is None:
                await app_db.dispose()

    docs = settings.api.docs_enabled
    app = FastAPI(
        title="IPDL",
        version=__version__,
        description="Реестр и аналитические портреты иностранных публичных должностных лиц.",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
        root_path=settings.api.root_path,
    )
    install_error_handlers(app)
    api = APIRouter(prefix=API_PREFIX)
    for module in (auth, meta, persons, exchange, sanctions, admin):
        api.include_router(module.router)
    app.include_router(api)
    app.include_router(meta.health_router)

    if settings.api.metrics_enabled:

        @app.get("/metrics", include_in_schema=False)
        async def metrics() -> Response:
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    _install_middleware(app)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    return app


def _install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > _MAX_BODY:
                response: Response = JSONResponse(
                    error_body("payload_too_large", "Запрос слишком большой"), status_code=413
                )
            else:
                response = await call_next(request)
        finally:
            structlog.contextvars.unbind_contextvars("request_id")
        elapsed = time.perf_counter() - started
        route = _route_template(request)
        HTTP_DURATION.labels(request.method, route, str(response.status_code)).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if route not in {"/healthz", "/readyz", "/metrics"}:
            log.info(
                "http_request",
                method=request.method,
                route=route,
                status=response.status_code,
                ms=round(elapsed * 1000, 1),
            )
        return response


def _route_template(request: Request) -> str:
    """Шаблон маршрута (``/api/v1/persons/{person_id}``) — иначе метрики разрастаются."""
    route = request.scope.get("route")
    template = getattr(route, "path_format", None) or getattr(route, "path", None)
    return str(template) if template else "unmatched"
