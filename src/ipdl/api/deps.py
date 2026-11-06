"""Зависимости FastAPI: состояние, сессия БД, текущий пользователь, роли, CSRF, аудит."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ipdl.api.errors import APIError
from ipdl.api.state import AppState
from ipdl.auth.service import AuthError, resolve_session
from ipdl.db.models import AuditEvent, AuthSession, Role, User

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.ipdl
    return state


State = Annotated[AppState, Depends(get_state)]


async def get_session(state: State) -> AsyncIterator[AsyncSession]:
    """Сессия на запрос; изменяющие маршруты сами вызывают ``commit()`` до ответа."""
    async with state.db.sessionmaker() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]


def client_ip(request: Request) -> str | None:
    # uvicorn с --proxy-headers уже подставил адрес клиента из X-Forwarded-For доверенного прокси
    return request.client.host if request.client else None


async def get_auth_session(request: Request, state: State, session: Session) -> AuthSession:
    auth = state.settings.auth
    token = request.cookies.get(auth.session_cookie)
    if not token:
        raise APIError(401, "unauthenticated", "Требуется вход в систему")
    try:
        auth_session = await resolve_session(session, token)
    except AuthError as exc:
        raise APIError(401, exc.code, exc.message) from exc
    if session.dirty:  # обновлён last_seen_at
        await session.commit()
    if request.method not in _SAFE_METHODS:
        cookie = request.cookies.get(auth.csrf_cookie, "")
        header = request.headers.get(auth.csrf_header, "")
        if not cookie or not hmac.compare_digest(cookie, header):
            raise APIError(403, "csrf_failed", "Проверка CSRF не пройдена — обновите страницу")
    return auth_session


CurrentSession = Annotated[AuthSession, Depends(get_auth_session)]


async def get_current_user(auth_session: CurrentSession) -> User:
    return auth_session.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: Role) -> Callable[[User], Coroutine[Any, Any, User]]:
    allowed = frozenset(roles)

    async def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise APIError(403, "forbidden", "Недостаточно прав для этого действия")
        return user

    return dependency


Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Editor = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST))]
Internal = Annotated[User, Depends(require_roles(Role.ADMIN, Role.ANALYST, Role.VIEWER))]


def audit(
    session: AsyncSession,
    request: Request | None,
    user: User | None,
    action: str,
    *,
    object_type: str | None = None,
    object_id: object | None = None,
    details: dict[str, Any] | None = None,
    username: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            user_id=user.id if user else None,
            username=(user.username if user else username),
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            ip=client_ip(request) if request else None,
            details=details,
        )
    )
