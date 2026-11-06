"""Санкционные списки: состояние, обновление, ручной скрининг."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from ipdl.api.deps import Admin, Internal, Session, State, audit
from ipdl.api.schemas import JobAccepted, SanctionsListOut, SanctionsSearchOut
from ipdl.db.models import SanctionsList
from ipdl.sanctions.service import list_statuses, screen

router = APIRouter(prefix="/sanctions", tags=["sanctions"])


@router.get("/lists")
async def lists(_user: Internal, state: State, session: Session) -> list[SanctionsListOut]:
    stale_after = state.settings.sanctions.stale_after_hours * 3600
    now = datetime.now(UTC)
    rows = (await session.scalars(select(SanctionsList).order_by(SanctionsList.id))).all()
    statuses = {s.id: s for s in await list_statuses(session)}
    return [
        SanctionsListOut(
            **statuses[row.id].model_dump(),
            url=row.url,
            status=row.status,
            error=row.error,
            stale=row.fetched_at is None or (now - row.fetched_at).total_seconds() > stale_after,
        )
        for row in rows
    ]


@router.post("/update", status_code=202)
async def update(request: Request, user: Admin, state: State, session: Session) -> JobAccepted:
    job = await state.queue.enqueue_sanctions_update(force=False)
    audit(session, request, user, "sanctions_update_requested")
    await session.commit()
    return JobAccepted(job=job)


@router.get("/search")
async def search(
    user: Internal,
    request: Request,
    state: State,
    session: Session,
    q: Annotated[str, Query(min_length=3, max_length=200)],
    birth_date: Annotated[date | None, Query()] = None,
    kind: Annotated[Literal["person", "entity"], Query()] = "person",
) -> SanctionsSearchOut:
    matches = await screen(
        session,
        [q],
        birth_date=birth_date,
        entity_types=(kind,),
        threshold=state.settings.sanctions.match_threshold,
        limit=state.settings.sanctions.max_matches,
        sources=state.sanctions_sources,
    )
    audit(
        session,
        request,
        user,
        "sanctions_search",
        details={"query": q, "kind": kind, "matches": len(matches)},
    )
    result = SanctionsSearchOut(query=q, matches=matches, lists=await list_statuses(session))
    await session.commit()
    return result
