"""Таблицы PostgreSQL (SQLAlchemy 2.0, типизированный ORM).

Перечисления хранятся строками с CHECK-ограничением (``native_enum=False``) — миграции
не требуют ``ALTER TYPE``. Портрет хранится как JSONB целиком (``Portrait``), а в
``persons`` дублируются поля для списка реестра и фильтров.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map: dict[Any, Any] = {  # noqa: RUF012 — так требует SQLAlchemy
        dict[str, Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


def _enum(enum_cls: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda cls: [m.value for m in cls],
    )


class Role(StrEnum):
    ADMIN = "admin"  # пользователи, партнёры, справочники + всё, что аналитик
    ANALYST = "analyst"  # проверки, решения, экспорт, обмен с партнёрами
    VIEWER = "viewer"  # просмотр реестра (внутренний)
    PARTNER = "partner"  # зарубежное ПФР: только переданные ему портреты


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RequestDirection(StrEnum):
    INCOMING = "incoming"  # обращение партнёра к нам
    OUTGOING = "outgoing"  # наш запрос / передача партнёру


class RequestKind(StrEnum):
    INFO_REQUEST = "info_request"
    DISCLOSURE = "disclosure"


class RequestStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Partner(Base):
    """Зарубежное подразделение финансовой разведки (ПФР) — сторона обмена."""

    __tablename__ = "partners"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    country: Mapped[str] = mapped_column(String(2))
    name: Mapped[str] = mapped_column(String(200))
    contact: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (UniqueConstraint("country", "name", name="uq_partners_country_name"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "user_role"))
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("partners.id", ondelete="RESTRICT")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]

    partner: Mapped[Partner | None] = relationship(lazy="joined")


class AuthSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))

    user: Mapped[User] = relationship(lazy="joined")

    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)


class Person(Base):
    """Карточка реестра. Сводные поля обновляются из текущей версии портрета."""

    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    full_name: Mapped[str] = mapped_column(String(200))
    latin_name: Mapped[str | None] = mapped_column(String(200))
    birth_date: Mapped[date | None] = mapped_column(Date)
    citizenship: Mapped[str | None] = mapped_column(String(2))
    context: Mapped[str | None] = mapped_column(Text)
    # Скелеты имён (names.match.fold) для нечёткого поиска по реестру (pg_trgm)
    search_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    pep_category: Mapped[str | None] = mapped_column(String(32))
    pep_tenure: Mapped[str | None] = mapped_column(String(16))
    position: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    risk_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[str | None] = mapped_column(String(16))
    current_portrait_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portraits.id", ondelete="SET NULL", use_alter=True)
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_persons_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
        Index("ix_persons_updated_at", "updated_at"),
    )


class Portrait(Base):
    """Версия портрета = фоновая задача сбора + результат + решение аналитика."""

    __tablename__ = "portraits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"))
    stage: Mapped[str | None] = mapped_column(String(32))
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    params: Mapped[dict[str, Any]]
    data: Mapped[dict[str, Any] | None]
    review: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    reviewed_at: Mapped[datetime | None]

    __table_args__ = (
        UniqueConstraint("person_id", "version", name="uq_portraits_person_version"),
        Index("ix_portraits_status", "status"),
    )


class ExchangeRequest(Base):
    """Журнал обращений: запросы и передачи сведений между ПФР."""

    __tablename__ = "requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"))
    partner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("partners.id", ondelete="RESTRICT"))
    portrait_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portraits.id", ondelete="SET NULL")
    )
    direction: Mapped[RequestDirection] = mapped_column(
        _enum(RequestDirection, "request_direction")
    )
    kind: Mapped[RequestKind] = mapped_column(_enum(RequestKind, "request_kind"))
    status: Mapped[RequestStatus] = mapped_column(_enum(RequestStatus, "request_status"))
    purpose: Mapped[str] = mapped_column(Text)
    legal_basis: Mapped[str | None] = mapped_column(Text)
    response_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    closed_at: Mapped[datetime | None]

    partner: Mapped[Partner] = relationship(lazy="joined")

    __table_args__ = (
        Index("ix_requests_person_id", "person_id"),
        Index("ix_requests_partner_kind", "partner_id", "kind"),
    )


class AuditEvent(Base):
    """Журнал действий пользователей (только добавление)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None]

    __table_args__ = (
        Index("ix_audit_events_at", "at"),
        Index("ix_audit_events_object", "object_type", "object_id"),
    )


class SanctionsList(Base):
    __tablename__ = "sanctions_lists"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(32))
    published_at: Mapped[date | None] = mapped_column(Date)
    fetched_at: Mapped[datetime | None]
    sha256: Mapped[str | None] = mapped_column(String(64))
    entries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="never", server_default="never")
    error: Mapped[str | None] = mapped_column(Text)


class SanctionsEntryRow(Base):
    __tablename__ = "sanctions_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    list_id: Mapped[str] = mapped_column(
        ForeignKey("sanctions_lists.id", ondelete="CASCADE"), index=True
    )
    ref: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(16))
    primary_name: Mapped[str] = mapped_column(Text)
    birth_dates: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    nationalities: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    programs: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    listed_on: Mapped[str | None] = mapped_column(String(10))
    remarks: Mapped[str | None] = mapped_column(Text)


class SanctionsName(Base):
    __tablename__ = "sanctions_names"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("sanctions_entries.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    folded: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        Index(
            "ix_sanctions_names_folded_trgm",
            "folded",
            postgresql_using="gin",
            postgresql_ops={"folded": "gin_trgm_ops"},
        ),
    )
