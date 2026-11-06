"""Схемы запросов и ответов HTTP API (контракт с веб-интерфейсом, см. web/src/lib/api)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ipdl.analysis.model import (
    FactorKey,
    FactorOverride,
    PepCategory,
    PepTenure,
    Portrait,
    Review,
    SanctionsListStatus,
    SanctionsMatch,
    Verification,
)
from ipdl.db.models import JobStatus, RequestDirection, RequestKind, RequestStatus, Role


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _country(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if len(value) != 2 or not value.isalpha():
        raise ValueError("код страны ISO 3166-1 alpha-2, например KZ")
    return value.upper()


# ---------------------------------------------------------------- служебное


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class MetaOut(BaseModel):
    system_name: str
    authority: str
    home_country: str
    legal_notice: str
    version: str


# ---------------------------------------------------------------- партнёры и пользователи


class PartnerOut(_Out):
    id: uuid.UUID
    country: str
    name: str
    contact: str | None
    is_active: bool


class PartnerIn(_In):
    country: str = Field(min_length=2, max_length=2)
    name: str = Field(min_length=2, max_length=200)
    contact: str | None = Field(default=None, max_length=1000)

    _c = field_validator("country")(_country)


class PartnerUpdate(_In):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    contact: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class UserOut(_Out):
    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    partner: PartnerOut | None
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class UserIn(_In):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=8, max_length=256)
    role: Role
    partner_id: uuid.UUID | None = None


class UserUpdate(_In):
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    role: Role | None = None
    partner_id: uuid.UUID | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


class LoginIn(_In):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(_In):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class MeOut(BaseModel):
    user: UserOut
    expires_at: datetime


# ---------------------------------------------------------------- реестр


class PersonIn(_In):
    full_name: str = Field(min_length=3, max_length=200)
    latin_name: str | None = Field(default=None, max_length=200)
    birth_date: date | None = None
    citizenship: str | None = None
    context: str | None = Field(default=None, max_length=500)

    _c = field_validator("citizenship")(_country)

    @field_validator("latin_name", "context")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return value or None


class PersonCreate(PersonIn):
    build: bool = True


class PersonUpdate(_In):
    full_name: str | None = Field(default=None, min_length=3, max_length=200)
    latin_name: str | None = Field(default=None, max_length=200)
    birth_date: date | None = None
    citizenship: str | None = None
    context: str | None = Field(default=None, max_length=500)

    _c = field_validator("citizenship")(_country)


class PortraitMeta(_Out):
    id: uuid.UUID
    version: int
    status: JobStatus
    stage: str | None
    progress: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    reviewed_at: datetime | None
    created_by_name: str | None = None
    score: int | None = None
    level: str | None = None


class PersonSummary(_Out):
    id: uuid.UUID
    full_name: str
    latin_name: str | None
    birth_date: date | None
    citizenship: str | None
    context: str | None
    pep_category: PepCategory | None
    pep_tenure: PepTenure | None
    position: str | None
    organization: str | None
    country: str | None
    risk_score: int | None
    risk_level: str | None
    created_at: datetime
    updated_at: datetime
    latest: PortraitMeta | None = None


class PersonList(BaseModel):
    items: list[PersonSummary]
    total: int
    page: int
    page_size: int


class RequestOut(_Out):
    id: uuid.UUID
    partner: PartnerOut
    portrait_id: uuid.UUID | None
    direction: RequestDirection
    kind: RequestKind
    status: RequestStatus
    purpose: str
    legal_basis: str | None
    response_note: str | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    created_by_name: str | None = None


class RequestIn(_In):
    partner_id: uuid.UUID
    kind: RequestKind
    direction: RequestDirection = RequestDirection.OUTGOING
    purpose: str = Field(min_length=3, max_length=2000)
    legal_basis: str | None = Field(default=None, max_length=1000)


class RequestUpdate(_In):
    status: RequestStatus | None = None
    response_note: str | None = Field(default=None, max_length=4000)


class PortraitOut(BaseModel):
    meta: PortraitMeta
    person_id: uuid.UUID
    portrait: Portrait | None
    review: Review | None


class PersonDetail(BaseModel):
    person: PersonSummary
    current: PortraitOut | None
    versions: list[PortraitMeta]
    requests: list[RequestOut]
    can_edit: bool


class ReviewIn(_In):
    pep_category: PepCategory | None = None
    pep_tenure: PepTenure | None = None
    pep_comment: str | None = Field(default=None, max_length=2000)
    conclusion: str | None = Field(default=None, max_length=5000)
    factors: dict[FactorKey, FactorOverride] = Field(default_factory=dict)
    sources: dict[str, Verification] = Field(default_factory=dict)


# ---------------------------------------------------------------- санкции, методика, аудит


class SanctionsListOut(SanctionsListStatus):
    url: str
    status: str
    error: str | None
    stale: bool


class SanctionsSearchOut(BaseModel):
    query: str
    matches: list[SanctionsMatch]
    lists: list[SanctionsListStatus]


class JobAccepted(BaseModel):
    job: str
    status: Literal["queued"] = "queued"


class AuditEventOut(_Out):
    id: int
    at: datetime
    username: str | None
    action: str
    object_type: str | None
    object_id: str | None
    ip: str | None
    details: dict[str, object] | None


class AuditList(BaseModel):
    items: list[AuditEventOut]
    total: int
