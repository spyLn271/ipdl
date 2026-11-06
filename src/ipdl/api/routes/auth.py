"""Вход, выход, текущий пользователь, смена пароля."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response

from ipdl.api.deps import CurrentSession, CurrentUser, Session, State, audit, client_ip
from ipdl.api.errors import APIError
from ipdl.api.metrics import LOGINS
from ipdl.api.schemas import LoginIn, MeOut, PasswordChange, UserOut
from ipdl.auth.service import (
    AuthError,
    PasswordPolicyError,
    authenticate,
    hash_password,
    logout,
    revoke_user_sessions,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookies(response: Response, state: State, token: str, csrf: str, max_age: int) -> None:
    auth = state.settings.auth
    # Сессия недоступна JavaScript; CSRF-токен фронтенд читает и отправляет в заголовке
    for name, value, httponly in (
        (auth.session_cookie, token, True),
        (auth.csrf_cookie, csrf, False),
    ):
        response.set_cookie(
            name,
            value,
            max_age=max_age,
            secure=auth.cookie_secure,
            httponly=httponly,
            samesite="lax",
            path="/",
        )


@router.post("/login")
async def login(
    body: LoginIn, request: Request, response: Response, state: State, session: Session
) -> MeOut:
    error: AuthError | None = None
    try:
        new = await authenticate(
            session,
            body.username,
            body.password,
            state.settings.auth,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        error = exc
        audit(session, request, None, "login_failed", username=body.username[:64].lower())
    else:
        audit(session, request, new.user, "login")
    # Счётчик неудачных попыток сохраняется и при ошибке входа
    await session.commit()
    if error is not None:
        LOGINS.labels("failed" if error.code != "locked" else "locked").inc()
        raise APIError(401, error.code, error.message)
    LOGINS.labels("ok").inc()
    ttl = state.settings.auth.session_ttl_hours * 3600
    _set_cookies(response, state, new.token, new.csrf, ttl)
    await session.refresh(new.user)
    return MeOut(user=UserOut.model_validate(new.user), expires_at=new.expires_at)


@router.post("/logout", status_code=204)
async def logout_route(
    request: Request, auth_session: CurrentSession, state: State, session: Session
) -> Response:
    auth = state.settings.auth
    token = request.cookies.get(auth.session_cookie, "")
    await logout(session, token)
    audit(session, request, auth_session.user, "logout")
    await session.commit()
    response = Response(status_code=204)
    response.delete_cookie(auth.session_cookie, path="/")
    response.delete_cookie(auth.csrf_cookie, path="/")
    return response


@router.get("/me")
async def me(auth_session: CurrentSession) -> MeOut:
    return MeOut(user=UserOut.model_validate(auth_session.user), expires_at=auth_session.expires_at)


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordChange, request: Request, user: CurrentUser, state: State, session: Session
) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        raise APIError(400, "invalid_password", "Текущий пароль указан неверно")
    try:
        user.password_hash = hash_password(body.new_password, state.settings.auth)
    except PasswordPolicyError as exc:
        raise APIError(422, "weak_password", str(exc)) from exc
    user.password_changed_at = datetime.now(UTC)
    await revoke_user_sessions(session, user.id)
    audit(session, request, user, "password_changed", object_type="user", object_id=user.id)
    await session.commit()
    response = Response(status_code=204)
    response.delete_cookie(state.settings.auth.session_cookie, path="/")
    return response
