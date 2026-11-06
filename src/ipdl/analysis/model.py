"""Модель аналитического портрета — общий контракт пайплайна, API, интерфейса и экспорта.

Каждый факт, извлечённый из открытых источников, несёт ``evidence``: идентификатор источника
и дословную цитату. Факты без подтверждающей цитаты в портрет не попадают (см. ``llm.extract``).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    NO_DATA = "no_data"


class PepCategory(StrEnum):
    """Категория по пп. 3-3) ст. 1 Закона РК № 191-IV (см. docs/METHODOLOGY.md)."""

    FOREIGN = "foreign"  # абз. 6–7: должность / публичная функция иностранного государства
    INTERNATIONAL_ORG = "international_org"  # абз. 8: руководящая должность в межгос. организации
    DOMESTIC = "domestic"  # абз. 2–5: ПДЛ Республики Казахстан
    FAMILY_OR_ASSOCIATE = "family_or_associate"  # супруг(а), близкий родственник, соратник ПДЛ
    NOT_PEP = "not_pep"  # публичная функция в источниках не найдена
    UNDETERMINED = "undetermined"  # данных недостаточно для вывода


class PepTenure(StrEnum):
    CURRENT = "current"
    FORMER = "former"
    UNKNOWN = "unknown"


class PositionCategory(StrEnum):
    STATE_BODY = (
        "state_body"  # законодательный, исполнительный, административный, судебный орган, ВС
    )
    PUBLIC_FUNCTION = "public_function"  # иная публичная функция для государства (госкомпании, ЦБ…)
    INTERNATIONAL_ORG = "international_org"  # организация, созданная государствами по договору
    POLITICAL_PARTY = "political_party"
    PRIVATE_SECTOR = "private_sector"
    NON_PROFIT = "non_profit"  # спортивные федерации, НКО, международные НПО
    OTHER = "other"


class RelationKind(StrEnum):
    SPOUSE = "spouse"
    CHILD = "child"
    PARENT = "parent"
    SIBLING = "sibling"
    OTHER_RELATIVE = "other_relative"
    BUSINESS_PARTNER = "business_partner"
    ASSOCIATE = "associate"


class CompanyRole(StrEnum):
    FOUNDER = "founder"
    OWNER = "owner"
    SHAREHOLDER = "shareholder"
    BENEFICIAL_OWNER = "beneficial_owner"
    DIRECTOR = "director"
    EXECUTIVE = "executive"
    OTHER = "other"


class AdverseCategory(StrEnum):
    CORRUPTION = "corruption"
    MONEY_LAUNDERING = "money_laundering"
    FRAUD = "fraud"
    SANCTIONS = "sanctions"
    TAX = "tax"
    TERRORISM = "terrorism"
    ORGANIZED_CRIME = "organized_crime"
    OTHER = "other"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LegalKind(StrEnum):
    CRIMINAL_CASE = "criminal_case"
    INVESTIGATION = "investigation"
    CONVICTION = "conviction"
    CIVIL_CASE = "civil_case"
    REGULATORY_ACTION = "regulatory_action"


class SourceKind(StrEnum):
    OFFICIAL = "official"  # госорганы, реестры, регуляторы, межгосударственные организации
    REFERENCE = "reference"  # энциклопедии и справочники
    MEDIA = "media"
    CORPORATE = "corporate"  # сайты компаний, отчётность
    OTHER = "other"


class Verification(StrEnum):
    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"


class FactorKey(StrEnum):
    POSITION = "position"
    JURISDICTION = "jurisdiction"
    WEALTH = "wealth"
    SANCTIONS = "sanctions"
    LEGAL = "legal"
    ADVERSE_MEDIA = "adverse_media"
    RELATED = "related"
    TRANSACTIONS = "transactions"


# ---------------------------------------------------------------- запрос


class Subject(_Model):
    """Что ввёл аналитик: исходные данные для поиска."""

    full_name: str = Field(min_length=3, max_length=200)
    latin_name: str | None = Field(default=None, max_length=200)
    birth_date: date | None = None
    citizenship: str | None = Field(default=None, min_length=2, max_length=2)
    context: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- источники и факты


class Source(_Model):
    id: str  # «S1», «S2»… — на них ссылаются факты
    url: str
    title: str
    domain: str
    kind: SourceKind
    snippet: str = ""
    published: date | None = None
    retrieved_at: datetime
    engines: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    relevance: float = 0
    fetched: bool = False
    analyzed: bool = False  # передан модели для извлечения фактов
    facts: int = 0  # сколько фактов с подтверждённой цитатой дал источник
    verification: Verification = Verification.UNVERIFIED  # из решения аналитика


class Evidence(_Model):
    source_id: str
    quote: str


class Position(_Model):
    title: str
    organization: str | None = None
    country: str | None = None  # ISO 3166-1 alpha-2
    start: str | None = None  # «2019» или «2019-05-14»
    end: str | None = None
    is_current: bool | None = None
    category: PositionCategory = PositionCategory.OTHER
    evidence: list[Evidence] = Field(default_factory=list)


class Relation(_Model):
    name: str
    relation: RelationKind
    note: str | None = None
    is_public_official: bool | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class Company(_Model):
    name: str
    role: CompanyRole = CompanyRole.OTHER
    share_percent: float | None = Field(default=None, ge=0, le=100)
    country: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class AdverseItem(_Model):
    category: AdverseCategory
    summary: str
    date: str | None = None
    severity: Severity = Severity.LOW
    evidence: list[Evidence] = Field(default_factory=list)


class LegalMatter(_Model):
    kind: LegalKind
    summary: str
    jurisdiction: str | None = None
    status: str | None = None
    date: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class TimelineEvent(_Model):
    date: str
    summary: str
    kind: str = "event"  # position | event | registry | risk
    source_id: str | None = None


class FieldValue(_Model):
    value: str
    evidence: list[Evidence] = Field(default_factory=list)


class Identity(_Model):
    full_name: str
    latin_name: str | None = None
    birth_date: FieldValue | None = None
    birth_place: FieldValue | None = None
    citizenship: list[str] = Field(default_factory=list)
    # Поля, по которым источники расходятся: значения — все найденные варианты
    conflicts: dict[str, list[str]] = Field(default_factory=dict)


# ---------------------------------------------------------------- санкции


class SanctionsListStatus(_Model):
    id: str
    name: str
    published_at: datetime | None = None
    fetched_at: datetime | None = None
    entries: int = 0


class SanctionsMatch(_Model):
    query: str | None = None  # какое имя проверялось (для связанных лиц и компаний)
    entity_type: str = "person"  # person | entity — по записи в списке
    list_id: str
    list_name: str
    entry_ref: str
    matched_name: str
    primary_name: str
    score: float
    birth_dates: list[str] = Field(default_factory=list)
    nationalities: list[str] = Field(default_factory=list)
    programs: list[str] = Field(default_factory=list)
    listed_on: str | None = None
    url: str | None = None
    # True — дата рождения совпала, False — противоречит, None — сравнить не с чем
    dob_match: bool | None = None


class SanctionsCheck(_Model):
    checked_at: datetime
    lists: list[SanctionsListStatus] = Field(default_factory=list)
    matches: list[SanctionsMatch] = Field(default_factory=list)
    # Совпадения связанных лиц и компаний из портрета
    related: list[SanctionsMatch] = Field(default_factory=list)


# ---------------------------------------------------------------- выводы


class PepAssessment(_Model):
    category: PepCategory
    tenure: PepTenure = PepTenure.UNKNOWN
    clause: str | None = None  # норма закона, на которой основан вывод
    rationale: str
    basis: list[int] = Field(default_factory=list)  # индексы positions / relations
    measures: list[str] = Field(default_factory=list)


class Factor(_Model):
    key: FactorKey
    level: RiskLevel
    auto_level: RiskLevel
    weight: float
    comment: str
    evidence: list[str] = Field(default_factory=list)  # id источников
    overridden: bool = False


class RiskAssessment(_Model):
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    method: str
    method_title: str
    factors: list[Factor]
    floors: list[str] = Field(default_factory=list)
    assessed_at: datetime
    next_review: date


class FactorOverride(_Model):
    level: RiskLevel
    comment: str = Field(min_length=3, max_length=1000)


class Review(_Model):
    """Решение аналитика поверх автоматического результата (хранится отдельно)."""

    reviewer: str | None = None
    reviewed_at: datetime | None = None
    pep_category: PepCategory | None = None
    pep_tenure: PepTenure | None = None
    pep_comment: str | None = Field(default=None, max_length=2000)
    conclusion: str | None = Field(default=None, max_length=5000)
    factors: dict[FactorKey, FactorOverride] = Field(default_factory=dict)
    sources: dict[str, Verification] = Field(default_factory=dict)


class RunStats(_Model):
    search_ok: bool = True
    llm_used: bool = False
    queries: int = 0
    results: int = 0
    sources: int = 0
    fetched: int = 0
    analyzed: int = 0
    duration_s: float = 0
    model: str | None = None


class Portrait(_Model):
    subject: Subject
    identity: Identity
    pep: PepAssessment
    risk: RiskAssessment
    positions: list[Position] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    companies: list[Company] = Field(default_factory=list)
    adverse: list[AdverseItem] = Field(default_factory=list)
    legal: list[LegalMatter] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    sanctions: SanctionsCheck
    sources: list[Source] = Field(default_factory=list)
    conclusion: str
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: RunStats = Field(default_factory=RunStats)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
