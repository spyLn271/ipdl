"""Сведение фактов из разных источников: дубликаты объединяются, доказательства копятся.

Источники часто пересказывают друг друга: одна и та же должность или публикация встречается
в пяти статьях. Дубликаты определяются нечётким сравнением названий, у объединённого факта —
все цитаты (чем больше независимых источников, тем надёжнее факт). Расхождения в
идентификационных данных (две разные даты рождения) не «усредняются», а показываются.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime

from rapidfuzz.fuzz import partial_token_set_ratio, token_set_ratio

from ipdl.analysis.model import (
    AdverseItem,
    Company,
    Evidence,
    FieldValue,
    Identity,
    LegalMatter,
    Position,
    PositionCategory,
    Relation,
    Subject,
    TimelineEvent,
)
from ipdl.geo import to_iso2
from ipdl.llm.extract import SourceFacts, normalize_text
from ipdl.names.match import fold, name_similarity

_SIMILAR = 85
_MAX_EVIDENCE = 6


def _similar(a: str | None, b: str | None, threshold: int = _SIMILAR) -> bool:
    if not a or not b:
        return not a and not b
    return token_set_ratio(normalize_text(a), normalize_text(b)) >= threshold


def _merge_evidence(target: list[Evidence], extra: Iterable[Evidence]) -> None:
    seen = {(e.source_id, e.quote) for e in target}
    for item in extra:
        if len(target) >= _MAX_EVIDENCE:
            return
        if (item.source_id, item.quote) not in seen and item.source_id not in {
            e.source_id for e in target
        }:
            target.append(item)
            seen.add((item.source_id, item.quote))


def _dedupe[T: (Position, Relation, Company, AdverseItem, LegalMatter)](
    items: Iterable[T], same: Callable[[T, T], bool], merge: Callable[[T, T], None]
) -> list[T]:
    result: list[T] = []
    for item in items:
        for existing in result:
            if same(existing, item):
                merge(existing, item)
                _merge_evidence(existing.evidence, item.evidence)
                break
        else:
            result.append(item.model_copy(deep=True))
    # Чем больше источников подтверждают факт, тем выше он в списке
    result.sort(key=lambda x: len({e.source_id for e in x.evidence}), reverse=True)
    return result


# ---------------------------------------------------------------- должности


def _folded_ratio(a: str | None, b: str | None) -> float:
    """Сходство после транслитерации: «Президент ФИДЕ» ≈ «President of FIDE»."""
    if not a or not b:
        return 0.0
    return float(token_set_ratio(fold(a), fold(b)))


def _same_position(a: Position, b: Position) -> bool:
    title = _folded_ratio(a.title, b.title)
    if not (a.organization and b.organization):
        return title >= _SIMILAR
    organization = _folded_ratio(a.organization, b.organization)
    # Одна организация и похожая должность — одна и та же позиция на разных языках
    return (title >= _SIMILAR and organization >= 75) or (organization >= 90 and title >= 60)


_CATEGORY_PRIORITY = {
    PositionCategory.STATE_BODY: 6,
    PositionCategory.INTERNATIONAL_ORG: 5,
    PositionCategory.PUBLIC_FUNCTION: 4,
    PositionCategory.POLITICAL_PARTY: 3,
    PositionCategory.PRIVATE_SECTOR: 2,
    PositionCategory.NON_PROFIT: 2,
    PositionCategory.OTHER: 0,
}


def _merge_position(a: Position, b: Position) -> None:
    a.organization = a.organization or b.organization
    a.country = a.country or b.country
    a.start = _earliest(a.start, b.start)
    a.end = a.end or b.end
    if a.is_current is None:
        a.is_current = b.is_current
    if a.category is PositionCategory.OTHER:
        a.category = b.category


_HEAD_OF_STATE = re.compile(
    r"(президент|president|премьер|prime minister|король|king|эмир|emir|канцлер|chancellor|"
    r"председатель правительства|head of (state|government))",
    re.IGNORECASE,
)
_SENIOR = re.compile(
    r"(министр|minister|глава|head|председатель|chair|губернатор|governor|аким|мэр|mayor|"
    r"посол|ambassador|депутат|deputy|сенатор|senator|судья|judge|генерал|general)",
    re.IGNORECASE,
)


def _seniority(title: str) -> int:
    """Чем выше должность, тем раньше в списке: глава государства важнее зам. министра."""
    if _HEAD_OF_STATE.search(title) and not re.search(
        r"(вице|vice|заместител|deputy)", title, re.IGNORECASE
    ):
        return 2
    return 1 if _SENIOR.search(title) else 0


def _earliest(a: str | None, b: str | None) -> str | None:
    if a and b:
        return min(a, b)
    return a or b


# ---------------------------------------------------------------- связи, компании, негатив


def _same_relation(a: Relation, b: Relation) -> bool:
    return name_similarity(a.name, b.name) >= 90


def _merge_relation(a: Relation, b: Relation) -> None:
    a.note = a.note or b.note
    if a.is_public_official is not True:
        a.is_public_official = b.is_public_official or a.is_public_official


def _same_company(a: Company, b: Company) -> bool:
    return _similar(a.name, b.name, 90)


def _merge_company(a: Company, b: Company) -> None:
    a.country = a.country or b.country
    a.share_percent = a.share_percent if a.share_percent is not None else b.share_percent


def _same_adverse(a: AdverseItem, b: AdverseItem) -> bool:
    if a.category != b.category:
        return False
    if a.date and b.date and a.date[:4] != b.date[:4]:
        return False
    return _similar(a.summary, b.summary, 70)


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


def _merge_adverse(a: AdverseItem, b: AdverseItem) -> None:
    a.date = a.date or b.date
    if _SEVERITY_ORDER[b.severity] > _SEVERITY_ORDER[a.severity]:
        a.severity = b.severity


def _same_legal(a: LegalMatter, b: LegalMatter) -> bool:
    if a.date and b.date and a.date[:4] != b.date[:4]:
        return False
    return _similar(a.summary, b.summary, 70)


def _merge_legal(a: LegalMatter, b: LegalMatter) -> None:
    a.date = a.date or b.date
    a.status = a.status or b.status
    a.jurisdiction = a.jurisdiction or b.jurisdiction


# ---------------------------------------------------------------- идентификация


def _vote(values: Sequence[FieldValue]) -> tuple[FieldValue | None, list[str]]:
    """Самое частое значение и список всех различных значений (если их больше одного)."""
    if not values:
        return None, []
    counts = Counter(normalize_text(v.value) for v in values)
    winner_key, _ = counts.most_common(1)[0]
    winner: FieldValue | None = None
    for value in values:
        if normalize_text(value.value) == winner_key:
            if winner is None:
                winner = value.model_copy(deep=True)
            else:
                _merge_evidence(winner.evidence, value.evidence)
    distinct = list(dict.fromkeys(v.value for v in values))
    return winner, distinct if len(counts) > 1 else []


def _birth_conflict(values: Sequence[str]) -> bool:
    """«1987» и «1987-11-13» не противоречат друг другу, «1987-11-13» и «1986» — да."""
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            if not (a.startswith(b) or b.startswith(a)):
                return True
    return False


def _places_differ(values: Sequence[str]) -> bool:
    """Разные ли это места: «д. Солтанишки, Вороновский р-н» и «деревня Солтанишки» — одно."""
    folded = [fold(v) for v in values]
    for i, a in enumerate(folded):
        for b in folded[i + 1 :]:
            if partial_token_set_ratio(a, b) < 85:
                return True
    return False


def build_identity(subject: Subject, latin: str | None, facts: Sequence[SourceFacts]) -> Identity:
    identity = Identity(full_name=subject.full_name, latin_name=subject.latin_name or latin)
    conflicts: dict[str, list[str]] = {}

    birth_values = [f.birth_date for f in facts if f.birth_date]
    if subject.birth_date is not None:
        identity.birth_date = FieldValue(value=subject.birth_date.isoformat())
        found = [v.value for v in birth_values]
        if found and _birth_conflict([identity.birth_date.value, *found]):
            conflicts["birth_date"] = list(dict.fromkeys([identity.birth_date.value, *found]))
    else:
        precise = sorted(birth_values, key=lambda v: len(v.value), reverse=True)
        winner, distinct = _vote(precise)
        identity.birth_date = winner
        if distinct and _birth_conflict(distinct):
            conflicts["birth_date"] = distinct

    places = [f.birth_place for f in facts if f.birth_place]
    # «Москва» и «Россия» не противоречат друг другу: страна без города в голосовании не участвует
    cities = [p for p in places if to_iso2(p.value) is None] or places
    winner, distinct = _vote(cities)
    identity.birth_place = winner
    if _places_differ(distinct):
        conflicts["birth_place"] = distinct

    citizenship = Counter(c.value for f in facts for c in f.citizenship)
    codes = [subject.citizenship] if subject.citizenship else []
    codes.extend(code for code, _ in citizenship.most_common() if code not in codes)
    identity.citizenship = codes
    identity.conflicts = conflicts
    return identity


# ---------------------------------------------------------------- хронология


def build_timeline(
    positions: Sequence[Position],
    events: Iterable[TimelineEvent],
    adverse: Sequence[AdverseItem],
    legal: Sequence[LegalMatter],
) -> list[TimelineEvent]:
    items: list[TimelineEvent] = []
    for position in positions:
        where = f", {position.organization}" if position.organization else ""
        source = position.evidence[0].source_id if position.evidence else None
        if position.start:
            items.append(
                TimelineEvent(
                    date=position.start,
                    summary=f"Начало работы: {position.title}{where}",
                    kind="position",
                    source_id=source,
                )
            )
        if position.end:
            items.append(
                TimelineEvent(
                    date=position.end,
                    summary=f"Окончание работы: {position.title}{where}",
                    kind="position",
                    source_id=source,
                )
            )
    dated: list[tuple[str, AdverseItem | LegalMatter]] = [
        *(("adverse", a) for a in adverse),
        *(("legal", m) for m in legal),
    ]
    items.extend(
        TimelineEvent(
            date=item.date,
            summary=item.summary,
            kind=kind,
            source_id=item.evidence[0].source_id if item.evidence else None,
        )
        for kind, item in dated
        if item.date
    )
    items.extend(events)
    unique: list[TimelineEvent] = []
    for event in sorted(items, key=lambda e: e.date):
        if any(
            e.date[:4] == event.date[:4] and _similar(e.summary, event.summary, 75) for e in unique
        ):
            continue
        unique.append(event)
    return unique


def merge_facts(
    facts: Sequence[SourceFacts],
) -> tuple[
    list[Position],
    list[Relation],
    list[Company],
    list[AdverseItem],
    list[LegalMatter],
    list[TimelineEvent],
]:
    usable = [f for f in facts if f.about_subject != "no"]
    positions = _dedupe((p for f in usable for p in f.positions), _same_position, _merge_position)
    for position in positions:
        if (
            position.is_current is None
            and position.end
            and position.end[:4] < str(datetime.now(UTC).year)
        ):
            position.is_current = False
    positions.sort(
        key=lambda p: (
            _CATEGORY_PRIORITY[p.category],
            _seniority(p.title),
            p.is_current is True,
            p.start or "",
        ),
        reverse=True,
    )
    relations = _dedupe((r for f in usable for r in f.relations), _same_relation, _merge_relation)
    companies = _dedupe((c for f in usable for c in f.companies), _same_company, _merge_company)
    adverse = _dedupe((a for f in usable for a in f.adverse), _same_adverse, _merge_adverse)
    legal = _dedupe((m for f in usable for m in f.legal), _same_legal, _merge_legal)
    events = [e for f in usable for e in f.events]
    return positions, relations, companies, adverse, legal, events
