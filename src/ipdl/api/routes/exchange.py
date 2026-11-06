"""Обмен с зарубежными ПФР: справочник партнёров и журнал обращений."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ipdl.api.deps import Admin, CurrentUser, Internal, Session, audit
from ipdl.api.errors import APIError
from ipdl.api.registry import get_person_for, request_out, user_names
from ipdl.api.schemas import (
    PartnerIn,
    PartnerOut,
    PartnerUpdate,
    RequestIn,
    RequestOut,
    RequestUpdate,
)
from ipdl.db.models import (
    ExchangeRequest,
    JobStatus,
    Partner,
    Person,
    RequestDirection,
    RequestKind,
    RequestStatus,
    Role,
)
from ipdl.db.models import Portrait as PortraitRow

router = APIRouter(tags=["exchange"])


# ---------------------------------------------------------------- партнёры


@router.get("/partners")
async def list_partners(_user: Internal, session: Session) -> list[PartnerOut]:
    rows = await session.scalars(select(Partner).order_by(Partner.country, Partner.name))
    return [PartnerOut.model_validate(p) for p in rows]


@router.post("/partners", status_code=201)
async def create_partner(
    body: PartnerIn, request: Request, user: Admin, session: Session
) -> PartnerOut:
    partner = Partner(country=body.country, name=body.name, contact=body.contact)
    session.add(partner)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise APIError(409, "duplicate", "Такой партнёр уже есть в справочнике") from exc
    audit(session, request, user, "partner_created", object_type="partner", object_id=partner.id)
    await session.commit()
    return PartnerOut.model_validate(partner)


@router.patch("/partners/{partner_id}")
async def update_partner(
    partner_id: uuid.UUID, body: PartnerUpdate, request: Request, user: Admin, session: Session
) -> PartnerOut:
    partner = await session.get(Partner, partner_id)
    if partner is None:
        raise APIError(404, "not_found", "Партнёр не найден")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(partner, field, value)
    audit(session, request, user, "partner_updated", object_type="partner", object_id=partner.id)
    await session.commit()
    return PartnerOut.model_validate(partner)


# ---------------------------------------------------------------- журнал обращений


@router.post("/persons/{person_id}/requests", status_code=201)
async def create_request(
    person_id: uuid.UUID, body: RequestIn, request: Request, user: CurrentUser, session: Session
) -> RequestOut:
    """Записать обращение.

    * аналитик: запрос доп. информации у ПФР партнёра (``info_request``, исходящий) или
      передача портрета (``disclosure``) — партнёр получает доступ к действующей версии;
    * пользователь-партнёр: запрос доп. информации по переданному ему лицу (входящий).
    """
    person = await get_person_for(session, user, person_id)
    if user.role is Role.VIEWER:
        raise APIError(403, "forbidden", "Недостаточно прав для этого действия")
    partner_id = body.partner_id
    direction, kind = body.direction, body.kind
    if user.role is Role.PARTNER:
        if user.partner_id is None or body.kind is not RequestKind.INFO_REQUEST:
            raise APIError(403, "forbidden", "Партнёр может только запросить информацию")
        partner_id, direction = user.partner_id, RequestDirection.INCOMING
    partner = await session.get(Partner, partner_id)
    if partner is None or not partner.is_active:
        raise APIError(422, "validation_error", "Партнёр не найден или отключён")

    portrait_id = None
    status = RequestStatus.OPEN
    if kind is RequestKind.DISCLOSURE:
        portrait_id = await _current_done_portrait(session, person)
        direction, status = RequestDirection.OUTGOING, RequestStatus.CLOSED
    row = ExchangeRequest(
        person_id=person.id,
        partner_id=partner.id,
        portrait_id=portrait_id,
        direction=direction,
        kind=kind,
        status=status,
        purpose=body.purpose,
        legal_basis=body.legal_basis,
        created_by=user.id,
        closed_at=datetime.now(UTC) if status is RequestStatus.CLOSED else None,
    )
    session.add(row)
    await session.flush()
    audit(
        session,
        request,
        user,
        f"request_{kind.value}",
        object_type="person",
        object_id=person.id,
        details={"partner": f"{partner.country} · {partner.name}", "request_id": str(row.id)},
    )
    await session.commit()
    await session.refresh(row)
    return request_out(row, await user_names(session, [row.created_by]))


async def _current_done_portrait(session: Session, person: Person) -> uuid.UUID:
    row = None
    if person.current_portrait_id is not None:
        row = await session.get(PortraitRow, person.current_portrait_id)
    if row is None or row.status is not JobStatus.DONE:
        raise APIError(409, "not_ready", "Нет построенного портрета для передачи партнёру")
    return row.id


@router.patch("/requests/{request_id}")
async def update_request(
    request_id: uuid.UUID,
    body: RequestUpdate,
    request: Request,
    user: CurrentUser,
    session: Session,
) -> RequestOut:
    row = await session.get(ExchangeRequest, request_id)
    if row is None:
        raise APIError(404, "not_found", "Обращение не найдено")
    if user.role not in {Role.ADMIN, Role.ANALYST}:
        raise APIError(403, "forbidden", "Недостаточно прав для этого действия")
    if row.kind is RequestKind.DISCLOSURE:
        raise APIError(409, "immutable", "Запись о передаче сведений не изменяется")
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        row.status = changes["status"]
        row.closed_at = datetime.now(UTC) if row.status is RequestStatus.CLOSED else None
    if "response_note" in changes:
        row.response_note = changes["response_note"]
    row.updated_at = datetime.now(UTC)
    audit(
        session,
        request,
        user,
        "request_updated",
        object_type="request",
        object_id=row.id,
        details={"status": row.status.value},
    )
    await session.commit()
    await session.refresh(row)
    return request_out(row, await user_names(session, [row.created_by]))
