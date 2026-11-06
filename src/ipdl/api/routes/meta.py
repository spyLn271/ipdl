"""Сведения о системе, методика оценки, проверки здоровья."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ipdl import __version__
from ipdl.api.deps import CurrentUser, State
from ipdl.api.schemas import MetaOut

router = APIRouter(tags=["meta"])
health_router = APIRouter(include_in_schema=False)


@router.get("/meta")
async def meta(state: State) -> MetaOut:
    """Публичные реквизиты для страницы входа и подвала (без авторизации)."""
    org = state.settings.org
    return MetaOut(
        system_name=org.system_name,
        authority=org.authority,
        home_country=org.home_country,
        legal_notice=org.legal_notice,
        version=__version__,
    )


@router.get("/methodology")
async def methodology(_user: CurrentUser, state: State) -> dict[str, Any]:
    return {
        "risk_model": state.risk_model.model_dump(mode="json"),
        "jurisdictions": state.jurisdictions.model_dump(mode="json"),
        "sanctions_sources": [s.model_dump() for s in state.sanctions_sources],
    }


@health_router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/readyz")
async def readyz(state: State) -> JSONResponse:
    checks = {"database": await state.db.ping(), "queue": await state.queue.ping()}
    ready = all(checks.values())
    return JSONResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )
