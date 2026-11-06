"""Реестр: карточки лиц, версии портретов, решение аналитика, экспорт."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import func, or_, select

from ipdl.analysis.model import PepCategory, Review, RiskLevel
from ipdl.api.deps import CurrentUser, Editor, Session, State, audit
from ipdl.api.errors import APIError
from ipdl.api.registry import (
    disclosed_portrait_ids,
    effective_portrait,
    get_person_for,
    get_portrait_for,
    latest_portraits,
    new_portrait,
    person_summary,
    portrait_meta,
    portrait_out,
    refresh_person,
    request_out,
    search_text,
    user_names,
)
from ipdl.api.schemas import (
    PersonCreate,
    PersonDetail,
    PersonList,
    PersonSummary,
    PersonUpdate,
    PortraitMeta,
    PortraitOut,
    ReviewIn,
)
from ipdl.db.models import (
    ExchangeRequest,
    JobStatus,
    Person,
    RequestKind,
    Role,
)
from ipdl.db.models import Portrait as PortraitRow
from ipdl.logs import get_logger
from ipdl.names.match import fold
from ipdl.report.render import render_docx, render_pdf

log = get_logger(__name__)
router = APIRouter(tags=["registry"])

_EDIT_ROLES = frozenset({Role.ADMIN, Role.ANALYST})


@router.get("/persons")
async def list_persons(
    user: CurrentUser,
    session: Session,
    q: Annotated[str | None, Query(max_length=200)] = None,
    pep: Annotated[PepCategory | None, Query()] = None,
    level: Annotated[RiskLevel | None, Query()] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> PersonList:
    stmt = select(Person)
    if user.role is Role.PARTNER:
        disclosed = select(ExchangeRequest.person_id).where(
            ExchangeRequest.partner_id == user.partner_id,
            ExchangeRequest.kind == RequestKind.DISCLOSURE,
        )
        stmt = stmt.where(Person.id.in_(disclosed))
    if pep is not None:
        stmt = stmt.where(Person.pep_category == pep.value)
    if level is not None:
        stmt = stmt.where(Person.risk_level == level.value)
    order = [Person.updated_at.desc()]
    if q and (needle := fold(q)):
        similarity = func.word_similarity(needle, Person.search_text)
        stmt = stmt.where(or_(Person.search_text.ilike(f"%{needle}%"), similarity > 0.45))
        order = [similarity.desc(), *order]
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    persons = (
        await session.scalars(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))
    ).all()
    latest = await latest_portraits(session, [p.id for p in persons])
    return PersonList(
        items=[person_summary(p, latest.get(p.id)) for p in persons],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/persons", status_code=201)
async def create_person(
    body: PersonCreate, request: Request, user: Editor, state: State, session: Session
) -> PersonSummary:
    person = Person(
        full_name=body.full_name,
        latin_name=body.latin_name,
        birth_date=body.birth_date,
        citizenship=body.citizenship,
        context=body.context,
        created_by=user.id,
    )
    person.search_text = search_text(person)
    session.add(person)
    await session.flush()
    row = await new_portrait(session, state, person, user) if body.build else None
    audit(session, request, user, "person_created", object_type="person", object_id=person.id)
    await session.commit()
    if row is not None:
        await state.queue.enqueue_portrait(row.id)
    await session.refresh(person)
    return person_summary(person, row)


@router.get("/persons/{person_id}")
async def get_person(
    person_id: uuid.UUID, request: Request, user: CurrentUser, state: State, session: Session
) -> PersonDetail:
    person = await get_person_for(session, user, person_id)
    rows = (
        await session.scalars(
            select(PortraitRow)
            .where(PortraitRow.person_id == person.id)
            .order_by(PortraitRow.version.desc())
        )
    ).all()
    requests_stmt = select(ExchangeRequest).where(ExchangeRequest.person_id == person.id)
    if user.role is Role.PARTNER:
        allowed = set(await disclosed_portrait_ids(session, user, person.id))
        rows = [r for r in rows if r.id in allowed]
        requests_stmt = requests_stmt.where(ExchangeRequest.partner_id == user.partner_id)
        current = rows[0] if rows else None
        audit(session, request, user, "partner_view", object_type="person", object_id=person.id)
        await session.commit()
    else:
        current = next((r for r in rows if r.id == person.current_portrait_id), None)
    requests = (
        await session.scalars(requests_stmt.order_by(ExchangeRequest.created_at.desc()))
    ).all()
    users = await user_names(
        session, [r.created_by for r in rows] + [r.created_by for r in requests]
    )
    latest = rows[0] if rows else None
    summary = person_summary(person, latest)
    if summary.latest:
        summary.latest.created_by_name = (
            users.get(latest.created_by) if latest and latest.created_by else None
        )
    return PersonDetail(
        person=summary,
        current=portrait_out(current, state, users) if current else None,
        versions=[portrait_meta(r, users) for r in rows],
        requests=[request_out(r, users) for r in requests],
        can_edit=user.role in _EDIT_ROLES,
    )


@router.patch("/persons/{person_id}")
async def update_person(
    person_id: uuid.UUID, body: PersonUpdate, request: Request, user: Editor, session: Session
) -> PersonSummary:
    person = await get_person_for(session, user, person_id)
    changes = body.model_dump(exclude_unset=True)
    if "full_name" in changes and not changes["full_name"]:
        raise APIError(422, "validation_error", "ФИО обязательно")
    for field, value in changes.items():
        # пустая строка в необязательном поле = «очистить»
        setattr(person, field, value if field == "full_name" else (value or None))
    person.search_text = search_text(person)
    person.updated_at = datetime.now(UTC)
    audit(
        session,
        request,
        user,
        "person_updated",
        object_type="person",
        object_id=person.id,
        details={"fields": sorted(changes)},
    )
    await session.commit()
    latest = (await latest_portraits(session, [person.id])).get(person.id)
    return person_summary(person, latest)


@router.delete("/persons/{person_id}", status_code=204)
async def delete_person(
    person_id: uuid.UUID, request: Request, user: CurrentUser, session: Session
) -> Response:
    if user.role is not Role.ADMIN:
        raise APIError(403, "forbidden", "Удалять записи реестра может только администратор")
    person = await get_person_for(session, user, person_id)
    audit(
        session,
        request,
        user,
        "person_deleted",
        object_type="person",
        object_id=person.id,
        details={"full_name": person.full_name},
    )
    await session.delete(person)
    await session.commit()
    return Response(status_code=204)


@router.post("/persons/{person_id}/portraits", status_code=202)
async def rebuild_portrait(
    person_id: uuid.UUID, request: Request, user: Editor, state: State, session: Session
) -> PortraitMeta:
    person = await get_person_for(session, user, person_id)
    row = await new_portrait(session, state, person, user)
    audit(session, request, user, "portrait_requested", object_type="portrait", object_id=row.id)
    await session.commit()
    await state.queue.enqueue_portrait(row.id)
    return portrait_meta(row)


@router.get("/portraits/{portrait_id}")
async def get_portrait(
    portrait_id: uuid.UUID, user: CurrentUser, state: State, session: Session
) -> PortraitOut:
    row = await get_portrait_for(session, user, portrait_id)
    users = await user_names(session, [row.created_by])
    return portrait_out(row, state, users)


@router.put("/portraits/{portrait_id}/review")
async def save_review(
    portrait_id: uuid.UUID,
    body: ReviewIn,
    request: Request,
    user: Editor,
    state: State,
    session: Session,
) -> PortraitOut:
    row = await get_portrait_for(session, user, portrait_id)
    if row.status is not JobStatus.DONE or row.data is None:
        raise APIError(409, "not_ready", "Портрет ещё не построен")
    known_sources = {s["id"] for s in row.data.get("sources", [])}
    unknown = set(body.sources) - known_sources
    if unknown:
        raise APIError(422, "validation_error", f"Неизвестные источники: {sorted(unknown)}")
    now = datetime.now(UTC)
    review = Review(**body.model_dump(), reviewer=user.display_name, reviewed_at=now)
    row.review = review.model_dump(mode="json")
    row.reviewed_at = now
    person = await session.get(Person, row.person_id)
    portrait = effective_portrait(row, state)
    if person is not None and portrait is not None and person.current_portrait_id == row.id:
        refresh_person(person, row, portrait)
    audit(
        session,
        request,
        user,
        "review_saved",
        object_type="portrait",
        object_id=row.id,
        details={
            "pep_category": body.pep_category,
            "factors": sorted(body.factors),
            "score": portrait.risk.score if portrait else None,
        },
    )
    await session.commit()
    users = await user_names(session, [row.created_by])
    return portrait_out(row, state, users)


@router.post("/portraits/{portrait_id}/current", status_code=204)
async def make_current(
    portrait_id: uuid.UUID, request: Request, user: Editor, state: State, session: Session
) -> Response:
    """Сделать версию действующей (например, вернуться к предыдущей)."""
    row = await get_portrait_for(session, user, portrait_id)
    portrait = effective_portrait(row, state)
    person = await session.get(Person, row.person_id)
    if portrait is None or person is None:
        raise APIError(409, "not_ready", "Портрет ещё не построен")
    refresh_person(person, row, portrait)
    audit(session, request, user, "portrait_made_current", object_type="portrait", object_id=row.id)
    await session.commit()
    return Response(status_code=204)


@router.get("/portraits/{portrait_id}/export.{fmt}")
async def export_portrait(
    portrait_id: uuid.UUID,
    fmt: str,
    request: Request,
    user: CurrentUser,
    state: State,
    session: Session,
) -> Response:
    if fmt not in {"docx", "pdf"}:
        raise APIError(404, "not_found", "Формат экспорта: docx или pdf")
    row = await get_portrait_for(session, user, portrait_id)
    portrait = effective_portrait(row, state)
    if portrait is None:
        raise APIError(409, "not_ready", "Портрет ещё не построен")
    review = Review.model_validate(row.review) if row.review else None
    org = state.settings.org
    if fmt == "docx":
        content = render_docx(portrait, review=review, org=org, version=row.version)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        content = await render_pdf(portrait, review=review, org=org, version=row.version)
        media = "application/pdf"
    audit(
        session,
        request,
        user,
        "portrait_exported",
        object_type="portrait",
        object_id=row.id,
        details={"format": fmt},
    )
    await session.commit()
    filename = f"Портрет ИПДЛ — {portrait.identity.full_name} — v{row.version}.{fmt}"
    ascii_name = f"ipdl-portrait-v{row.version}.{fmt}"
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
            ),
            "Cache-Control": "no-store",
        },
    )
