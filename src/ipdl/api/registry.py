"""Операции реестра поверх БД: карточки, версии портретов, доступ партнёров, сводные поля."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ipdl.analysis.conclusion import apply_review
from ipdl.analysis.model import Portrait, Review, Subject
from ipdl.api.errors import APIError
from ipdl.api.schemas import PersonSummary, PortraitMeta, PortraitOut, RequestOut
from ipdl.api.state import AppState
from ipdl.db.models import (
    ExchangeRequest,
    JobStatus,
    Person,
    RequestKind,
    Role,
    User,
)
from ipdl.db.models import Portrait as PortraitRow
from ipdl.names.match import fold


def search_text(person: Person, extra: Sequence[str] = ()) -> str:
    names = [person.full_name, person.latin_name or "", *extra]
    return " ".join(dict.fromkeys(fold(n) for n in names if n)).strip()


def subject_of(person: Person) -> Subject:
    return Subject(
        full_name=person.full_name,
        latin_name=person.latin_name,
        birth_date=person.birth_date,
        citizenship=person.citizenship,
        context=person.context,
    )


async def pending_jobs(session: AsyncSession) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PortraitRow)
        .where(PortraitRow.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
    )
    return int(count or 0)


async def new_portrait(
    session: AsyncSession, state: AppState, person: Person, user: User
) -> PortraitRow:
    if await pending_jobs(session) >= state.settings.jobs.max_pending:
        raise APIError(
            503, "queue_full", "Очередь построения портретов заполнена — повторите позже"
        )
    running = await session.scalar(
        select(PortraitRow.id).where(
            PortraitRow.person_id == person.id,
            PortraitRow.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    if running is not None:
        raise APIError(409, "already_running", "Портрет этого лица уже строится")
    version = await session.scalar(
        select(func.coalesce(func.max(PortraitRow.version), 0)).where(
            PortraitRow.person_id == person.id
        )
    )
    row = PortraitRow(
        person_id=person.id,
        version=int(version or 0) + 1,
        status=JobStatus.QUEUED,
        stage=None,
        progress=0,
        params=subject_of(person).model_dump(mode="json"),
        created_by=user.id,
    )
    session.add(row)
    await session.flush()
    return row


def effective_portrait(row: PortraitRow, state: AppState) -> Portrait | None:
    """Портрет с применённым решением аналитика (или ``None``, пока не построен)."""
    if row.data is None:
        return None
    portrait = Portrait.model_validate(row.data)
    review = Review.model_validate(row.review) if row.review else None
    return apply_review(
        portrait,
        review,
        model=state.risk_model,
        jurisdictions=state.jurisdictions,
        home_country=state.settings.org.home_country,
    )


def refresh_person(person: Person, row: PortraitRow, portrait: Portrait) -> None:
    """Обновить сводные поля карточки из действующей версии портрета."""
    person.current_portrait_id = row.id
    person.pep_category = portrait.pep.category.value
    person.pep_tenure = portrait.pep.tenure.value
    top = portrait.positions[0] if portrait.positions else None
    basis = [portrait.positions[i] for i in portrait.pep.basis if i < len(portrait.positions)]
    main = basis[0] if basis else top
    person.position = main.title if main else None
    person.organization = main.organization if main else None
    person.country = (main.country if main else None) or (
        portrait.identity.citizenship[0] if portrait.identity.citizenship else None
    )
    person.risk_score = portrait.risk.score
    person.risk_level = portrait.risk.level.value
    extra = [portrait.identity.latin_name or ""]
    person.search_text = search_text(person, extra)
    person.updated_at = datetime.now(UTC)


def portrait_meta(row: PortraitRow, users: dict[uuid.UUID, str] | None = None) -> PortraitMeta:
    score = level = None
    if row.data is not None:
        risk = row.data.get("risk", {})
        score, level = risk.get("score"), risk.get("level")
    meta = PortraitMeta.model_validate(row)
    meta.created_by_name = (users or {}).get(row.created_by) if row.created_by else None
    meta.score, meta.level = score, level
    return meta


def portrait_out(
    row: PortraitRow, state: AppState, users: dict[uuid.UUID, str] | None = None
) -> PortraitOut:
    return PortraitOut(
        meta=portrait_meta(row, users),
        person_id=row.person_id,
        portrait=effective_portrait(row, state),
        review=Review.model_validate(row.review) if row.review else None,
    )


def person_summary(person: Person, latest: PortraitRow | None) -> PersonSummary:
    summary = PersonSummary.model_validate(person)
    summary.latest = portrait_meta(latest) if latest else None
    return summary


async def latest_portraits(
    session: AsyncSession, person_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, PortraitRow]:
    if not person_ids:
        return {}
    newest = (
        select(PortraitRow.person_id, func.max(PortraitRow.version).label("v"))
        .where(PortraitRow.person_id.in_(person_ids))
        .group_by(PortraitRow.person_id)
        .subquery()
    )
    rows = await session.scalars(
        select(PortraitRow).join(
            newest,
            (PortraitRow.person_id == newest.c.person_id) & (PortraitRow.version == newest.c.v),
        )
    )
    return {row.person_id: row for row in rows}


async def user_names(
    session: AsyncSession, ids: Sequence[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(select(User.id, User.display_name).where(User.id.in_(wanted)))
    return {row.id: row.display_name for row in rows}


def request_out(row: ExchangeRequest, users: dict[uuid.UUID, str]) -> RequestOut:
    out = RequestOut.model_validate(row)
    out.created_by_name = users.get(row.created_by) if row.created_by else None
    return out


# ---------------------------------------------------------------- доступ партнёров


async def disclosed_portrait_ids(
    session: AsyncSession, user: User, person_id: uuid.UUID
) -> list[uuid.UUID]:
    """Версии портрета, переданные ПФР пользователя-партнёра (новые первыми)."""
    rows = await session.scalars(
        select(ExchangeRequest.portrait_id)
        .where(
            ExchangeRequest.person_id == person_id,
            ExchangeRequest.partner_id == user.partner_id,
            ExchangeRequest.kind == RequestKind.DISCLOSURE,
            ExchangeRequest.portrait_id.is_not(None),
        )
        .order_by(ExchangeRequest.created_at.desc())
    )
    return [pid for pid in rows if pid is not None]


async def get_person_for(session: AsyncSession, user: User, person_id: uuid.UUID) -> Person:
    person = await session.get(Person, person_id)
    if person is None:
        raise APIError(404, "not_found", "Лицо не найдено в реестре")
    if user.role is Role.PARTNER and not await disclosed_portrait_ids(session, user, person_id):
        # Не раскрываем партнёру даже факт наличия записи
        raise APIError(404, "not_found", "Лицо не найдено в реестре")
    return person


async def get_portrait_for(
    session: AsyncSession, user: User, portrait_id: uuid.UUID
) -> PortraitRow:
    row = await session.get(PortraitRow, portrait_id)
    if row is None:
        raise APIError(404, "not_found", "Портрет не найден")
    if user.role is Role.PARTNER and portrait_id not in await disclosed_portrait_ids(
        session, user, row.person_id
    ):
        raise APIError(404, "not_found", "Портрет не найден")
    return row
