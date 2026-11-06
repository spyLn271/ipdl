"""Администрирование: пользователи и журнал действий."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ipdl.api.deps import Admin, Session, State, audit
from ipdl.api.errors import APIError
from ipdl.api.schemas import AuditEventOut, AuditList, UserIn, UserOut, UserUpdate
from ipdl.auth.service import (
    PasswordPolicyError,
    hash_password,
    normalize_username,
    revoke_user_sessions,
)
from ipdl.db.models import AuditEvent, Partner, Role, User

router = APIRouter(tags=["admin"])


async def _check_partner(session: Session, role: Role, partner_id: uuid.UUID | None) -> None:
    if role is Role.PARTNER:
        if partner_id is None or await session.get(Partner, partner_id) is None:
            raise APIError(422, "validation_error", "Для роли «партнёр» укажите ПФР партнёра")
    elif partner_id is not None:
        raise APIError(
            422, "validation_error", "ПФР партнёра указывается только для роли «партнёр»"
        )


@router.get("/users")
async def list_users(_admin: Admin, session: Session) -> list[UserOut]:
    rows = await session.scalars(select(User).order_by(User.username))
    return [UserOut.model_validate(u) for u in rows]


@router.post("/users", status_code=201)
async def create_user(
    body: UserIn, request: Request, admin: Admin, state: State, session: Session
) -> UserOut:
    await _check_partner(session, body.role, body.partner_id)
    try:
        password_hash = hash_password(body.password, state.settings.auth)
    except PasswordPolicyError as exc:
        raise APIError(422, "weak_password", str(exc)) from exc
    user = User(
        username=normalize_username(body.username),
        display_name=body.display_name,
        password_hash=password_hash,
        role=body.role,
        partner_id=body.partner_id,
        password_changed_at=datetime.now(UTC),
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise APIError(409, "duplicate", "Пользователь с таким логином уже есть") from exc
    audit(
        session,
        request,
        admin,
        "user_created",
        object_type="user",
        object_id=user.id,
        details={"username": user.username, "role": user.role.value},
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    request: Request,
    admin: Admin,
    state: State,
    session: Session,
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise APIError(404, "not_found", "Пользователь не найден")
    changes = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (
        changes.get("is_active") is False or changes.get("role", Role.ADMIN) is not Role.ADMIN
    ):
        raise APIError(
            409, "self_lockout", "Нельзя отключить себя или снять с себя роль администратора"
        )
    role = changes.get("role", user.role)
    partner_id = changes.get("partner_id", user.partner_id if role is Role.PARTNER else None)
    await _check_partner(session, role, partner_id)
    user.role, user.partner_id = role, partner_id
    if changes.get("display_name"):
        user.display_name = changes["display_name"]
    revoke = False
    if "is_active" in changes and changes["is_active"] is not None:
        user.is_active = changes["is_active"]
        revoke = not user.is_active
    if changes.get("password"):
        try:
            user.password_hash = hash_password(changes["password"], state.settings.auth)
        except PasswordPolicyError as exc:
            raise APIError(422, "weak_password", str(exc)) from exc
        user.password_changed_at = datetime.now(UTC)
        user.failed_logins, user.locked_until = 0, None
        revoke = True
    if revoke or "role" in changes:
        await revoke_user_sessions(session, user.id)
    audit(
        session,
        request,
        admin,
        "user_updated",
        object_type="user",
        object_id=user.id,
        details={
            "fields": sorted(k for k in changes if k != "password")
            + (["password"] if changes.get("password") else [])
        },
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.get("/audit")
async def list_audit(
    _admin: Admin,
    session: Session,
    object_type: Annotated[str | None, Query(max_length=32)] = None,
    object_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditList:
    stmt = select(AuditEvent)
    if object_type:
        stmt = stmt.where(AuditEvent.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditEvent.object_id == object_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = await session.scalars(
        stmt.order_by(AuditEvent.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return AuditList(items=[AuditEventOut.model_validate(r) for r in rows], total=total)
