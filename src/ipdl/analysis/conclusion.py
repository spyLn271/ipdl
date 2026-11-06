"""Текст заключения для комплаенс-досье и применение решения аналитика к портрету."""

from __future__ import annotations

from ipdl.analysis.methodology import Jurisdictions, RiskModel
from ipdl.analysis.model import (
    FactorKey,
    PepAssessment,
    PepCategory,
    Portrait,
    Review,
    RiskAssessment,
    RiskLevel,
)
from ipdl.analysis.risk import RiskInputs, assess_risk

LEVEL_TITLES = {
    RiskLevel.LOW: "низкий",
    RiskLevel.MEDIUM: "средний",
    RiskLevel.HIGH: "высокий",
    RiskLevel.NO_DATA: "нет данных",
}
PEP_TITLES = {
    PepCategory.FOREIGN: "иностранное публичное должностное лицо (ИПДЛ)",
    PepCategory.INTERNATIONAL_ORG: "должностное лицо межгосударственной организации",
    PepCategory.DOMESTIC: "публичное должностное лицо Республики Казахстан",
    PepCategory.FAMILY_OR_ASSOCIATE: "связанное лицо публичного должностного лица",
    PepCategory.NOT_PEP: "статус ИПДЛ не подтверждён",
    PepCategory.UNDETERMINED: "статус не определён",
}

LIMITATIONS = [
    (
        "Портрет предварительный: это не официальное заключение и не результат полноценного "
        "санкционного, PEP/ИПДЛ или adverse media-скрининга. Сведения и ссылки необходимо "
        "перепроверить на дату принятия решения."
    ),
    "Отсутствие сведений в открытых источниках не означает их отсутствия в действительности.",
    (
        "Совпадения с санкционными списками — возможные: личность подтверждается по дате "
        "рождения, гражданству и документам."
    ),
    "Публикации СМИ не являются доказательством; факты подтверждаются официальными источниками.",
    (
        "Факты извлечены автоматически (локальная языковая модель) и сопровождаются цитатами — "
        "проверьте их по ссылкам на источники."
    ),
]


def write_conclusion(
    *,
    full_name: str,
    headline: str | None,
    pep: PepAssessment,
    risk: RiskAssessment,
) -> str:
    parts = [f"{full_name}" + (f" — {headline}." if headline else ".")]
    parts.append(pep.rationale)
    parts.append(
        f"Предварительный уровень риска: {LEVEL_TITLES[risk.level]} ({risk.score}/100, "
        f"методика {risk.method})."
    )
    high = [f for f in risk.factors if f.level is RiskLevel.HIGH]
    if high:
        parts.append("Факторы высокого риска: " + "; ".join(f.comment for f in high[:4]) + ".")
    if risk.floors:
        parts.append("Минимальный уровень установлен потому, что: " + "; ".join(risk.floors) + ".")
    if pep.category in {PepCategory.FOREIGN, PepCategory.INTERNATIONAL_ORG}:
        parts.append(
            "Применяются меры пункта 1 статьи 8 Закона РК № 191-IV, включая усиленную надлежащую "
            "проверку на постоянной основе и установление источника происхождения средств."
        )
    else:
        parts.append(
            "Окончательное решение принимается после проверки официальных и актуальных "
            "источников, критериев ПДЛ/ИПДЛ, связанных лиц, санкционных списков и негативных "
            "публикаций."
        )
    return " ".join(p.strip() for p in parts if p.strip())


def headline_of(portrait: Portrait) -> str | None:
    if portrait.positions:
        top = portrait.positions[0]
        return top.title + (f", {top.organization}" if top.organization else "")
    return None


def apply_review(
    portrait: Portrait,
    review: Review | None,
    *,
    model: RiskModel,
    jurisdictions: Jurisdictions,
    home_country: str,
) -> Portrait:
    """Действующий портрет = автоматический результат + решение аналитика."""
    if review is None:
        return portrait
    result = portrait.model_copy(deep=True)
    if review.pep_category is not None or review.pep_tenure is not None:
        pep = result.pep
        pep.category = review.pep_category or pep.category
        pep.tenure = review.pep_tenure or pep.tenure
        if review.pep_comment:
            pep.rationale = f"Решение аналитика: {review.pep_comment}"
    for source in result.sources:
        source.verification = review.sources.get(source.id, source.verification)
    result.risk = assess_risk(
        risk_inputs(result, home_country),
        model=model,
        jurisdictions=jurisdictions,
        review=review,
        now=portrait.risk.assessed_at,
    )
    result.conclusion = review.conclusion or write_conclusion(
        full_name=result.identity.full_name,
        headline=headline_of(result),
        pep=result.pep,
        risk=result.risk,
    )
    return result


def risk_inputs(portrait: Portrait, home_country: str) -> RiskInputs:
    return RiskInputs(
        pep=portrait.pep,
        identity=portrait.identity,
        positions=portrait.positions,
        relations=portrait.relations,
        companies=portrait.companies,
        adverse=portrait.adverse,
        legal=portrait.legal,
        sanctions=portrait.sanctions,
        home_country=home_country,
        search_ok=portrait.stats.search_ok,
        lists_loaded=bool(portrait.sanctions.lists),
    )


def factor(portrait: Portrait, key: FactorKey) -> RiskLevel:
    return next(f.level for f in portrait.risk.factors if f.key is key)
