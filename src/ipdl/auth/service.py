"""Пользователи и сессии.

* Пароли — Argon2id (pwdlib), минимальная длина из настроек.
* Сессия — случайный токен в httpOnly-cookie; в базе хранится только его SHA-256.
* CSRF — double-submit: cookie ``ipdl_csrf`` (читается фронтендом) должна совпасть с
  заголовком ``X-CSRF-Token`` у изменяющих запросов.
* Перебор паролей — блокировка учётной записи после N неудачных попыток на M минут.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ipdl.config.settings import AuthSettings
from ipdl.db.models import AuthSession, Role, User

_hasher = PasswordHash.recommended()
# Хэш для сравнения, когда пользователя нет: время ответа не выдаёт существование логина
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))
_TOUCH_INTERVAL = timedelta(minutes=5)


class AuthError(Exception):
    """Неверный логин/пароль, блокировка или истёкшая сессия."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PasswordPolicyError(ValueError):
    pass


def hash_password(password: str, settings: AuthSettings) -> str:
    check_password_policy(password, settings)
    return _hasher.hash(password)


def check_password_policy(password: str, settings: AuthSettings) -> None:
    if len(password) < settings.min_password_length:
        raise PasswordPolicyError(
            f"Пароль должен быть не короче {settings.min_password_length} символов"
        )
    if password.strip() != password or len(set(password)) < 5:
        raise PasswordPolicyError("Пароль слишком простой")


def verify_password(password: str, password_hash: str) -> bool:
    return bool(_hasher.verify(password, password_hash))


def normalize_username(username: str) -> str:
    return username.strip().lower()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(slots=True)
class NewSession:
    token: str
    csrf: str
    expires_at: datetime
    user: User


async def authenticate(
    session: AsyncSession,
    username: str,
    password: str,
    settings: AuthSettings,
    *,
    ip: str | None,
    user_agent: str | None,
) -> NewSession:
    now = datetime.now(UTC)
    user = await session.scalar(select(User).where(User.username == normalize_username(username)))
    if user is None:
        _hasher.verify(password, _DUMMY_HASH)
        raise AuthError("invalid_credentials", "Неверный логин или пароль")
    if user.locked_until and user.locked_until > now:
        raise AuthError("locked", "Учётная запись временно заблокирована после неудачных попыток")
    valid, updated_hash = _hasher.verify_and_update(password, user.password_hash)
    if not valid or not user.is_active:
        user.failed_logins += 1
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
        raise AuthError("invalid_credentials", "Неверный логин или пароль")
    if updated_hash:
        user.password_hash = updated_hash
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now

    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=settings.session_ttl_hours)
    session.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=expires_at,
            ip=(ip or "")[:64] or None,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return NewSession(token=token, csrf=secrets.token_urlsafe(24), expires_at=expires_at, user=user)


async def resolve_session(session: AsyncSession, token: str) -> AuthSession:
    now = datetime.now(UTC)
    row = await session.scalar(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    )
    if row is None or row.expires_at <= now:
        raise AuthError("unauthenticated", "Сессия истекла — войдите снова")
    if not row.user.is_active:
        raise AuthError("unauthenticated", "Учётная запись отключена")
    if now - row.last_seen_at > _TOUCH_INTERVAL:
        row.last_seen_at = now
    return row


async def logout(session: AsyncSession, token: str) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))


async def revoke_user_sessions(session: AsyncSession, user_id: object) -> None:
    await session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


async def purge_expired_sessions(session: AsyncSession) -> int:
    result = await session.execute(
        delete(AuthSession).where(AuthSession.expires_at <= datetime.now(UTC))
    )
    return int(getattr(result, "rowcount", 0) or 0)


INTERNAL_ROLES = frozenset({Role.ADMIN, Role.ANALYST, Role.VIEWER})
EDITOR_ROLES = frozenset({Role.ADMIN, Role.ANALYST})
