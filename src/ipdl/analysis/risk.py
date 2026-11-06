"""Оценка риска по восьми факторам (methodology/risk-model.yaml).

Уровень каждого фактора определяется явными правилами ниже; комментарий объясняет, из чего
он получен. Аналитик может переопределить уровень фактора с обоснованием — итог
пересчитывается, автоматический уровень сохраняется рядом (``auto_level``).
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from ipdl.analysis.methodology import Jurisdictions, RiskModel
from ipdl.analysis.model import (
    AdverseCategory,
    AdverseItem,
    Company,
    CompanyRole,
    Factor,
    FactorKey,
    Identity,
    LegalKind,
    LegalMatter,
    PepAssessment,
    PepCategory,
    PepTenure,
    Position,
    Relation,
    Review,
    RiskAssessment,
    RiskLevel,
    SanctionsCheck,
    Severity,
)
from ipdl.analysis.pep import position_category
from ipdl.geo import country_name

_OWNERSHIP = {
    CompanyRole.OWNER,
    CompanyRole.FOUNDER,
    CompanyRole.SHAREHOLDER,
    CompanyRole.BENEFICIAL_OWNER,
}
_SEVERITY_RANK = {Severity.LOW: 0, Severity.MEDIUM: 1, Severity.HIGH: 2}


@dataclass(slots=True)
class RiskInputs:
    pep: PepAssessment
    identity: Identity
    positions: Sequence[Position]
    relations: Sequence[Relation]
    companies: Sequence[Company]
    adverse: Sequence[AdverseItem]
    legal: Sequence[LegalMatter]
    sanctions: SanctionsCheck
    home_country: str
    search_ok: bool = True  # поиск по открытым источникам состоялся
    lists_loaded: bool = True  # санкционные списки загружены


@dataclass(slots=True)
class _Auto:
    level: RiskLevel
    comment: str
    evidence: list[str] = field(default_factory=list)


def _sources(items: Sequence[AdverseItem | LegalMatter | Company | Relation]) -> list[str]:
    return list(dict.fromkeys(e.source_id for item in items for e in item.evidence))[:8]


def _names(codes: Sequence[str]) -> str:
    return ", ".join(country_name(c) or c for c in codes)


# ---------------------------------------------------------------- факторы


def _position(inp: RiskInputs) -> _Auto:
    pep = inp.pep
    basis = [inp.positions[i] for i in pep.basis if i < len(inp.positions)]
    title = basis[0].title if basis else None
    sources = list(dict.fromkeys(e.source_id for p in basis for e in p.evidence))[:8]
    if pep.category in {PepCategory.FOREIGN, PepCategory.INTERNATIONAL_ORG}:
        if pep.tenure is PepTenure.FORMER:
            return _Auto(RiskLevel.MEDIUM, f"Бывшее ИПДЛ: {title}", sources)
        return _Auto(RiskLevel.HIGH, f"ИПДЛ: {title}", sources)
    if pep.category is PepCategory.DOMESTIC:
        return _Auto(RiskLevel.MEDIUM, f"ПДЛ Республики Казахстан: {title}", sources)
    if pep.category is PepCategory.FAMILY_OR_ASSOCIATE:
        return _Auto(RiskLevel.MEDIUM, "Связанное лицо публичного должностного лица", sources)
    if pep.category is PepCategory.NOT_PEP:
        top = inp.positions[0] if inp.positions else None
        comment = (
            f"Публичных должностей не найдено; основная деятельность: {top.title}"
            + (f", {top.organization}" if top and top.organization else "")
            if top
            else "Публичных должностей не найдено"
        )
        return _Auto(RiskLevel.LOW, comment, _sources([]))
    return _Auto(RiskLevel.NO_DATA, "Сведений о должностях недостаточно")


def _jurisdiction(inp: RiskInputs, jur: Jurisdictions) -> _Auto:
    countries = list(inp.identity.citizenship)
    countries.extend(
        p.country
        for p in inp.positions
        if p.country and position_category(p, inp.home_country) is not None
    )
    countries = list(dict.fromkeys(c.upper() for c in countries if c))
    if not countries:
        return _Auto(RiskLevel.NO_DATA, "Гражданство и страна деятельности не установлены")
    fatf = jur.fatf
    black = [c for c in countries if c in fatf.call_for_action]
    grey = [c for c in countries if c in fatf.increased_monitoring]
    national = [c for c in countries if c in jur.national_high_risk]
    offshore = [c for c in countries if c in jur.preferential_tax.codes]
    notes = [f"Страны: {_names(countries)}"]
    as_of = f"FATF на {fatf.as_of:%d.%m.%Y}"
    if black:
        notes.append(f"призыв FATF к контрмерам/усиленной проверке: {_names(black)} ({as_of})")
        return _Auto(RiskLevel.HIGH, "; ".join(notes))
    level = RiskLevel.LOW
    if grey:
        notes.append(f"под усиленным мониторингом FATF: {_names(grey)} ({as_of})")
        level = RiskLevel.MEDIUM
    if national:
        notes.append(f"в перечне повышенного риска организации: {_names(national)}")
        level = RiskLevel.MEDIUM
    if offshore:
        notes.append(
            f"государства с льготным налогообложением (Приказ МФ РК № 492): {_names(offshore)}"
        )
        level = RiskLevel.MEDIUM
    if level is RiskLevel.LOW:
        notes.append(f"не входят в списки FATF ({as_of}) и перечень льготного налогообложения")
    return _Auto(level, "; ".join(notes))


def _wealth(inp: RiskInputs, jur: Jurisdictions) -> _Auto:
    owned = [c for c in inp.companies if c.role in _OWNERSHIP]
    offshore = [
        c
        for c in owned
        if c.country
        and (c.country in jur.preferential_tax.codes or c.country in jur.fatf.call_for_action)
    ]
    tax = [
        a for a in inp.adverse if a.category in {AdverseCategory.TAX, AdverseCategory.CORRUPTION}
    ]
    if offshore:
        names = ", ".join(f"{c.name} ({c.country})" for c in offshore[:3])
        return _Auto(
            RiskLevel.HIGH,
            f"Владение компаниями в офшорных юрисдикциях / юрисдикциях высокого риска: {names}",
            _sources(offshore),
        )
    if owned or tax:
        parts = []
        if owned:
            names = ", ".join(c.name for c in owned[:4])
            parts.append(f"Доли в бизнесе: {names}")
        if tax:
            parts.append("публикации о налоговых нарушениях или коррупции")
        parts.append("источники благосостояния требуют подтверждения (декларации, отчётность)")
        return _Auto(RiskLevel.MEDIUM, "; ".join(parts), _sources([*owned, *tax]))
    return _Auto(RiskLevel.NO_DATA, "Сведений об активах и источниках дохода не найдено")


def _sanctions(inp: RiskInputs) -> _Auto:
    official = [m for m in inp.sanctions.matches if m.dob_match is not False]
    conflicting = [m for m in inp.sanctions.matches if m.dob_match is False]
    media = [a for a in inp.adverse if a.category is AdverseCategory.SANCTIONS]
    lists = ", ".join(s.name for s in inp.sanctions.lists) or "списки не загружены"
    if official:
        refs = "; ".join(f"{m.list_name}: {m.primary_name} ({m.entry_ref})" for m in official[:3])
        return _Auto(RiskLevel.HIGH, f"Возможное совпадение — требуется ручная проверка: {refs}")
    if media:
        worst = max(media, key=lambda a: _SEVERITY_RANK[a.severity])
        level = RiskLevel.HIGH if worst.severity is Severity.HIGH else RiskLevel.MEDIUM
        return _Auto(
            level,
            f"В официальных списках совпадений нет, но СМИ сообщают о санкциях: {worst.summary}",
            _sources(media),
        )
    if conflicting:
        refs = "; ".join(f"{m.list_name}: {m.primary_name}" for m in conflicting[:3])
        return _Auto(
            RiskLevel.MEDIUM,
            f"Совпадение по имени при другой дате рождения (вероятно, другое лицо): {refs}",
        )
    if not inp.lists_loaded:
        return _Auto(RiskLevel.NO_DATA, "Санкционные списки не загружены — скрининг не выполнен")
    return _Auto(RiskLevel.LOW, f"Совпадений не найдено: {lists}")


def _legal(inp: RiskInputs) -> _Auto:
    if not inp.legal:
        return _Auto(
            RiskLevel.NO_DATA,
            "В открытых источниках не найдено; нужен запрос в правоохранительные органы/ПФР",
        )
    serious = [m for m in inp.legal if m.kind in {LegalKind.CONVICTION, LegalKind.CRIMINAL_CASE}]
    medium = [
        m for m in inp.legal if m.kind in {LegalKind.INVESTIGATION, LegalKind.REGULATORY_ACTION}
    ]
    if serious:
        return _Auto(RiskLevel.HIGH, serious[0].summary, _sources(serious))
    if medium:
        return _Auto(RiskLevel.MEDIUM, medium[0].summary, _sources(medium))
    return _Auto(RiskLevel.LOW, inp.legal[0].summary, _sources(inp.legal))


def _adverse(inp: RiskInputs) -> _Auto:
    items = [a for a in inp.adverse if a.category is not AdverseCategory.SANCTIONS] or list(
        inp.adverse
    )
    if not inp.search_ok and not items:
        return _Auto(RiskLevel.NO_DATA, "Поиск по открытым источникам не выполнен")
    if not items:
        return _Auto(RiskLevel.LOW, "Негативных публикаций не найдено")
    counts = {s: sum(1 for a in items if a.severity is s) for s in Severity}
    sources = _sources(items)
    summary = (
        f"Публикаций: {len(items)} (высокая значимость — {counts[Severity.HIGH]}, "
        f"средняя — {counts[Severity.MEDIUM]}, низкая — {counts[Severity.LOW]}), "
        f"источников: {len(sources)}"
    )
    if counts[Severity.HIGH]:
        return _Auto(RiskLevel.HIGH, summary, sources)
    if counts[Severity.MEDIUM] or counts[Severity.LOW] >= 3:
        return _Auto(RiskLevel.MEDIUM, summary, sources)
    return _Auto(RiskLevel.LOW, summary, sources)


def _related(inp: RiskInputs, jur: Jurisdictions) -> _Auto:
    sanctioned = [m for m in inp.sanctions.related if m.dob_match is not False]
    companies = [m for m in sanctioned if m.entity_type != "person"]
    if companies:
        refs = "; ".join(f"{m.query} → {m.list_name}: {m.primary_name}" for m in companies[:3])
        return _Auto(RiskLevel.HIGH, f"Связанные компании в санкционных списках: {refs}")
    if sanctioned:
        # Даты рождения связанных лиц неизвестны: совпадение имени — повод для проверки
        refs = "; ".join(f"{m.query} → {m.list_name}: {m.primary_name}" for m in sanctioned[:3])
        return _Auto(
            RiskLevel.MEDIUM,
            f"Имена связанных лиц совпадают с записями санкционных списков (проверить): {refs}",
        )
    risky_companies = [
        c
        for c in inp.companies
        if c.country
        and (
            c.country in jur.fatf.call_for_action
            or c.country in jur.preferential_tax.codes
            or c.country in jur.national_high_risk
        )
    ]
    if risky_companies:
        names = ", ".join(f"{c.name} ({c.country})" for c in risky_companies[:3])
        return _Auto(
            RiskLevel.HIGH,
            f"Компании в офшорных юрисдикциях / юрисдикциях высокого риска: {names}",
            _sources(risky_companies),
        )
    officials = [r for r in inp.relations if r.is_public_official]
    if officials:
        names = ", ".join(r.name for r in officials[:3])
        return _Auto(
            RiskLevel.MEDIUM,
            f"Связи с публичными должностными лицами: {names}",
            _sources(officials),
        )
    if inp.relations or inp.companies:
        return _Auto(
            RiskLevel.LOW,
            f"Связанных лиц: {len(inp.relations)}, компаний: {len(inp.companies)}; "
            "признаков повышенного риска не найдено",
            _sources([*inp.relations, *inp.companies]),
        )
    return _Auto(RiskLevel.NO_DATA, "Связанные лица и компании не установлены")


def _transactions() -> _Auto:
    return _Auto(
        RiskLevel.NO_DATA,
        "Заполняется аналитиком по данным финансового мониторинга (СПО, пороговые операции)",
    )


# ---------------------------------------------------------------- итог


def assess_risk(
    inp: RiskInputs,
    *,
    model: RiskModel,
    jurisdictions: Jurisdictions,
    review: Review | None = None,
    now: datetime | None = None,
) -> RiskAssessment:
    auto = {
        FactorKey.POSITION: _position(inp),
        FactorKey.JURISDICTION: _jurisdiction(inp, jurisdictions),
        FactorKey.WEALTH: _wealth(inp, jurisdictions),
        FactorKey.SANCTIONS: _sanctions(inp),
        FactorKey.LEGAL: _legal(inp),
        FactorKey.ADVERSE_MEDIA: _adverse(inp),
        FactorKey.RELATED: _related(inp, jurisdictions),
        FactorKey.TRANSACTIONS: _transactions(),
    }
    overrides = review.factors if review else {}
    factors: list[Factor] = []
    for key, spec in model.factors.items():
        result = auto[key]
        override = overrides.get(key)
        factors.append(
            Factor(
                key=key,
                level=override.level if override else result.level,
                auto_level=result.level,
                weight=spec.weight,
                comment=override.comment if override else result.comment,
                evidence=result.evidence,
                overridden=override is not None,
            )
        )
    return score_factors(factors, inp, model=model, now=now)


def score_factors(
    factors: Sequence[Factor],
    inp: RiskInputs,
    *,
    model: RiskModel,
    now: datetime | None = None,
) -> RiskAssessment:
    total_weight = sum(f.weight for f in factors)
    raw = sum(
        f.weight * (model.no_data_points if f.level is RiskLevel.NO_DATA else model.points[f.level])
        for f in factors
    )
    score = round(raw / total_weight) if total_weight else 0
    floors: list[str] = []

    def floor(name: str) -> None:
        nonlocal score
        spec = model.floors.get(name)
        if spec and score < spec.min_score:
            score = spec.min_score
            floors.append(spec.reason)

    sanctions = next(f for f in factors if f.key is FactorKey.SANCTIONS)
    if any(m.dob_match is not False for m in inp.sanctions.matches) and (
        sanctions.level is RiskLevel.HIGH
    ):
        floor("sanctions_match")
    position = next(f for f in factors if f.key is FactorKey.POSITION)
    if inp.pep.category in {PepCategory.FOREIGN, PepCategory.INTERNATIONAL_ORG} and (
        position.level is not RiskLevel.LOW
    ):
        floor("foreign_pep_former" if inp.pep.tenure is PepTenure.FORMER else "foreign_pep_current")

    score = max(0, min(100, score))
    level = model.level_for(score)
    moment = now or datetime.now(UTC)
    months = model.review_months[level]
    return RiskAssessment(
        score=score,
        level=level,
        method=model.id,
        method_title=model.title,
        factors=list(factors),
        floors=floors,
        assessed_at=moment,
        next_review=_add_months(moment.date(), months),
    )


def _add_months(day: date, months: int) -> date:
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
