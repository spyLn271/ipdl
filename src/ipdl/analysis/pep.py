"""Предварительная классификация статуса ПДЛ/ИПДЛ по пп. 3-3) ст. 1 Закона РК № 191-IV.

Правила (без «чёрного ящика»):

* должность в органе власти иностранного государства (``state_body``, страна ≠ KZ) —
  ИПДЛ, абзац 6; иная публичная функция для иностранного государства — абзац 7;
* руководящая должность в межгосударственной организации — абзац 8;
* те же категории в Казахстане — ПДЛ РК, абзацы 2–5 (перечень Президента РК не проверяется);
* связь с публичным должностным лицом (супруг, родственник, соратник) — связанное лицо;
* частный бизнес, спорт, НКО сами по себе статуса не дают — «не ПДЛ»;
* нет сведений о должностях — «не определён».

Решение остаётся за аналитиком: он может изменить категорию с обоснованием (Review).
"""

from __future__ import annotations

from collections.abc import Sequence

from ipdl.analysis.methodology import RiskModel
from ipdl.analysis.model import (
    PepAssessment,
    PepCategory,
    PepTenure,
    Position,
    PositionCategory,
    Relation,
    RelationKind,
)
from ipdl.geo import country_name

_PUBLIC = {PositionCategory.STATE_BODY, PositionCategory.PUBLIC_FUNCTION}
_FAMILY = {
    RelationKind.SPOUSE,
    RelationKind.CHILD,
    RelationKind.PARENT,
    RelationKind.SIBLING,
    RelationKind.OTHER_RELATIVE,
}
_PRIORITY = [
    PepCategory.FOREIGN,
    PepCategory.INTERNATIONAL_ORG,
    PepCategory.DOMESTIC,
    PepCategory.FAMILY_OR_ASSOCIATE,
]


def position_category(position: Position, home_country: str) -> tuple[PepCategory, str] | None:
    """Категория ПДЛ, которую даёт одна должность, и абзац закона — или ``None``."""
    if position.category is PositionCategory.INTERNATIONAL_ORG:
        return PepCategory.INTERNATIONAL_ORG, "абз. 8"
    if position.category not in _PUBLIC or not position.country:
        return None
    if position.country.upper() == home_country.upper():
        return PepCategory.DOMESTIC, "абз. 2–5"
    paragraph = "абз. 6" if position.category is PositionCategory.STATE_BODY else "абз. 7"
    return PepCategory.FOREIGN, paragraph


def _tenure(positions: Sequence[Position]) -> PepTenure:
    if any(p.is_current is True for p in positions):
        return PepTenure.CURRENT
    if positions and all(p.is_current is False or p.end for p in positions):
        return PepTenure.FORMER
    return PepTenure.UNKNOWN


def _describe(position: Position) -> str:
    parts = [position.title]
    if position.organization:
        parts.append(position.organization)
    if position.country:
        parts.append(country_name(position.country) or position.country)
    period = "–".join(x for x in (position.start, position.end) if x)
    if period:
        parts.append(period)
    return ", ".join(parts)


def assess_pep(
    positions: Sequence[Position],
    relations: Sequence[Relation],
    *,
    home_country: str,
    model: RiskModel,
) -> PepAssessment:
    by_category: dict[PepCategory, list[tuple[int, Position, str]]] = {}
    unknown_country: list[Position] = []
    for index, position in enumerate(positions):
        result = position_category(position, home_country)
        if result is not None:
            category, paragraph = result
            by_category.setdefault(category, []).append((index, position, paragraph))
        elif position.category in _PUBLIC and not position.country:
            unknown_country.append(position)

    basis_law = model.legal_basis.get("pep_definition", {})
    clause_base = f"Закон РК № 191-IV, {basis_law.get('clause', 'пп. 3-3) ст. 1')}"

    for category in _PRIORITY[:3]:
        found = by_category.get(category)
        if not found:
            continue
        chosen = [p for _, p, _ in found]
        paragraphs = sorted({paragraph for _, _, paragraph in found})
        tenure = _tenure(chosen)
        described = "; ".join(_describe(p) for p in chosen[:3])
        if category is PepCategory.DOMESTIC:
            measures = [model.legal_basis.get("domestic_list", {}).get("note", "")]
            rationale = (
                f"В источниках указана должность в государственных органах (организациях) "
                f"Республики Казахстан: {described}. Это ПДЛ РК, а не ИПДЛ; меры п. 1 ст. 8 "
                f"применяются при включении в перечень, утверждаемый Президентом РК."
            )
        else:
            measures = model.measures
            kind = (
                "в органе власти или с публичной функцией иностранного государства"
                if category is PepCategory.FOREIGN
                else "в организации, созданной государствами на основе международного договора"
            )
            state = {
                PepTenure.CURRENT: "занимает",
                PepTenure.FORMER: "занимал(а) ранее",
                PepTenure.UNKNOWN: "занимает или занимал(а)",
            }[tenure]
            rationale = f"По данным источников лицо {state} должность {kind}: {described}."
        return PepAssessment(
            category=category,
            tenure=tenure,
            clause=f"{clause_base}, {', '.join(paragraphs)}",
            rationale=rationale,
            basis=[index for index, _, _ in found],
            measures=[m for m in measures if m],
        )

    linked = [
        (i, r)
        for i, r in enumerate(relations)
        if r.is_public_official is True
        and (
            r.relation in _FAMILY
            or r.relation in {RelationKind.ASSOCIATE, RelationKind.BUSINESS_PARTNER}
        )
    ]
    if linked:
        names = "; ".join(f"{r.name}" + (f" ({r.note})" if r.note else "") for _, r in linked[:3])
        family = any(r.relation in _FAMILY for _, r in linked)
        return PepAssessment(
            category=PepCategory.FAMILY_OR_ASSOCIATE,
            tenure=PepTenure.UNKNOWN,
            clause=(
                "Закон РК № 191-IV, пп. 1) п. 1 ст. 8 (супруг и близкие родственники ПДЛ)"
                if family
                else "Рекомендация 12 FATF (близкие соратники ПДЛ)"
            ),
            rationale=(
                "Собственная публичная должность в источниках не найдена, но указана связь "
                f"с публичным должностным лицом: {names}. Требуется проверка статуса этих лиц."
            ),
            basis=[i for i, _ in linked],
            measures=model.measures[:1],
        )

    if unknown_country:
        return PepAssessment(
            category=PepCategory.UNDETERMINED,
            rationale=(
                "Найдены публичные должности без указания государства: "
                f"{'; '.join(_describe(p) for p in unknown_country[:3])}. "
                "Нужно установить страну, чтобы отнести лицо к ИПДЛ или ПДЛ РК."
            ),
        )
    if positions:
        listed = "; ".join(_describe(p) for p in positions[:3])
        return PepAssessment(
            category=PepCategory.NOT_PEP,
            rationale=(
                "Статус ИПДЛ не подтверждён: в источниках найдены только должности вне "
                f"государственных органов и межгосударственных организаций ({listed}). "
                "Предпринимательская деятельность, руководство коммерческой компанией или "
                "спортивной организацией сами по себе не означают статуса ИПДЛ."
            ),
        )
    return PepAssessment(
        category=PepCategory.UNDETERMINED,
        rationale=(
            "Сведений о должностях в найденных источниках недостаточно для вывода о статусе."
        ),
    )
