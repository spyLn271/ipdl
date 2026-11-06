"""Русские подписи перечислений для экспорта (в интерфейсе — свои переводы ru/kk/en)."""

from __future__ import annotations

from ipdl.analysis.model import (
    AdverseCategory,
    CompanyRole,
    FactorKey,
    LegalKind,
    PepTenure,
    PositionCategory,
    RelationKind,
    RiskLevel,
    Severity,
    SourceKind,
    Verification,
)

LEVEL = {
    RiskLevel.LOW: "Низкий",
    RiskLevel.MEDIUM: "Средний",
    RiskLevel.HIGH: "Высокий",
    RiskLevel.NO_DATA: "Нет данных",
}
TENURE = {PepTenure.CURRENT: "действующий", PepTenure.FORMER: "бывший", PepTenure.UNKNOWN: "—"}
FACTOR = {
    FactorKey.POSITION: "Должность и уровень влияния",
    FactorKey.JURISDICTION: "Юрисдикция / страна",
    FactorKey.WEALTH: "Источники благосостояния",
    FactorKey.SANCTIONS: "Санкционные списки",
    FactorKey.LEGAL: "Уголовные дела и расследования",
    FactorKey.ADVERSE_MEDIA: "Негативные публикации в СМИ",
    FactorKey.RELATED: "Связанные лица и компании",
    FactorKey.TRANSACTIONS: "Финансовые операции в РК",
}
POSITION_CATEGORY = {
    PositionCategory.STATE_BODY: "государственный орган",
    PositionCategory.PUBLIC_FUNCTION: "публичная функция",
    PositionCategory.INTERNATIONAL_ORG: "межгосударственная организация",
    PositionCategory.POLITICAL_PARTY: "политическая партия",
    PositionCategory.PRIVATE_SECTOR: "частный сектор",
    PositionCategory.NON_PROFIT: "некоммерческая организация",
    PositionCategory.OTHER: "иное",
}
RELATION = {
    RelationKind.SPOUSE: "супруг(а)",
    RelationKind.CHILD: "ребёнок",
    RelationKind.PARENT: "родитель",
    RelationKind.SIBLING: "брат / сестра",
    RelationKind.OTHER_RELATIVE: "родственник",
    RelationKind.BUSINESS_PARTNER: "деловой партнёр",
    RelationKind.ASSOCIATE: "близкий соратник",
}
COMPANY_ROLE = {
    CompanyRole.FOUNDER: "учредитель",
    CompanyRole.OWNER: "владелец",
    CompanyRole.SHAREHOLDER: "акционер",
    CompanyRole.BENEFICIAL_OWNER: "бенефициар",
    CompanyRole.DIRECTOR: "директор",
    CompanyRole.EXECUTIVE: "руководитель",
    CompanyRole.OTHER: "иная роль",
}
ADVERSE = {
    AdverseCategory.CORRUPTION: "коррупция",
    AdverseCategory.MONEY_LAUNDERING: "отмывание денег",
    AdverseCategory.FRAUD: "мошенничество",
    AdverseCategory.SANCTIONS: "санкции",
    AdverseCategory.TAX: "налоги",
    AdverseCategory.TERRORISM: "терроризм",
    AdverseCategory.ORGANIZED_CRIME: "организованная преступность",
    AdverseCategory.OTHER: "иное",
}
SEVERITY = {Severity.LOW: "низкая", Severity.MEDIUM: "средняя", Severity.HIGH: "высокая"}
LEGAL = {
    LegalKind.CRIMINAL_CASE: "уголовное дело",
    LegalKind.INVESTIGATION: "расследование",
    LegalKind.CONVICTION: "приговор",
    LegalKind.CIVIL_CASE: "гражданский иск",
    LegalKind.REGULATORY_ACTION: "меры регулятора",
}
SOURCE_KIND = {
    SourceKind.OFFICIAL: "официальный",
    SourceKind.REFERENCE: "справочный",
    SourceKind.MEDIA: "СМИ",
    SourceKind.CORPORATE: "корпоративный",
    SourceKind.OTHER: "прочий",
}
DOB_MATCH: dict[bool | None, str] = {
    True: "дата рождения совпадает",
    False: "дата рождения отличается",
    None: "дату рождения сравнить не с чем",
}
VERIFICATION = {
    Verification.UNVERIFIED: "не проверен",
    Verification.CONFIRMED: "подтверждён",
    Verification.DISPUTED: "оспорен",
}
