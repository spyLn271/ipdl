from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ipdl.analysis.aggregate import build_identity, build_timeline, merge_facts
from ipdl.analysis.conclusion import apply_review, write_conclusion
from ipdl.analysis.methodology import RiskModel, load_jurisdictions, load_risk_model
from ipdl.analysis.model import (
    AdverseCategory,
    AdverseItem,
    Company,
    CompanyRole,
    Evidence,
    FactorKey,
    FactorOverride,
    FieldValue,
    Identity,
    LegalKind,
    LegalMatter,
    PepCategory,
    PepTenure,
    Position,
    PositionCategory,
    Relation,
    RelationKind,
    Review,
    RiskLevel,
    SanctionsCheck,
    Severity,
    Subject,
    Verification,
)
from ipdl.analysis.pep import assess_pep
from ipdl.analysis.risk import RiskInputs, assess_risk
from ipdl.llm.extract import SourceFacts
from tests.conftest import ROOT
from tests.fakes import match

MODEL = load_risk_model(ROOT / "methodology/risk-model.yaml")
JUR = load_jurisdictions(ROOT / "methodology/jurisdictions.yaml")
NOW = datetime(2026, 10, 27, tzinfo=UTC)


def ev(source: str = "S1") -> list[Evidence]:
    return [Evidence(source_id=source, quote="цитата из источника")]


def pos(title: str, category: PositionCategory, country: str | None, **kw: object) -> Position:
    return Position(title=title, category=category, country=country, evidence=ev(), **kw)  # type: ignore[arg-type]


# ---------------------------------------------------------------- методика


def test_methodology_files_are_valid() -> None:
    assert abs(sum(f.weight for f in MODEL.factors.values()) - 1) < 1e-9
    assert MODEL.level_for(0) is RiskLevel.LOW
    assert MODEL.level_for(34) is RiskLevel.MEDIUM
    assert MODEL.level_for(100) is RiskLevel.HIGH
    assert "KP" in JUR.fatf.call_for_action
    assert "BA" in JUR.fatf.increased_monitoring
    assert len(JUR.fatf.increased_monitoring) == 22
    assert "VG" in JUR.preferential_tax.codes
    assert JUR.fatf_is_stale(date(2027, 1, 1))
    assert not JUR.fatf_is_stale(date(2026, 7, 1))


def test_methodology_validation(tmp_path: Path) -> None:
    data = yaml.safe_load((ROOT / "methodology/risk-model.yaml").read_text(encoding="utf-8"))
    del data["factors"]["wealth"]
    with pytest.raises(ValidationError, match="нет факторов"):
        RiskModel.model_validate(data)
    data = yaml.safe_load((ROOT / "methodology/risk-model.yaml").read_text(encoding="utf-8"))
    data["bands"]["medium"] = [40, 66]
    with pytest.raises(ValidationError, match="подряд"):
        RiskModel.model_validate(data)


# ---------------------------------------------------------------- ПДЛ


@pytest.mark.parametrize(
    ("position", "category", "clause"),
    [
        (
            pos("Министр финансов", PositionCategory.STATE_BODY, "BY", is_current=True),
            PepCategory.FOREIGN,
            "абз. 6",
        ),
        (
            pos("Председатель правления", PositionCategory.PUBLIC_FUNCTION, "RU", is_current=True),
            PepCategory.FOREIGN,
            "абз. 7",
        ),
        (
            pos("Аким области", PositionCategory.STATE_BODY, "KZ", is_current=True),
            PepCategory.DOMESTIC,
            "абз. 2–5",
        ),
        (
            pos("Директор", PositionCategory.INTERNATIONAL_ORG, None, is_current=True),
            PepCategory.INTERNATIONAL_ORG,
            "абз. 8",
        ),
    ],
)
def test_pep_categories(position: Position, category: PepCategory, clause: str) -> None:
    pep = assess_pep([position], [], home_country="KZ", model=MODEL)
    assert pep.category is category
    assert pep.clause is not None and clause in pep.clause
    assert pep.basis == [0]


def test_pep_tenure() -> None:
    former = pos(
        "Посол", PositionCategory.STATE_BODY, "US", start="2010", end="2015", is_current=False
    )
    pep = assess_pep([former], [], home_country="KZ", model=MODEL)
    assert pep.tenure is PepTenure.FORMER
    assert "ранее" in pep.rationale
    assert len(pep.measures) == 5


def test_pep_family_member() -> None:
    relation = Relation(
        name="Пётр Иванов",
        relation=RelationKind.SPOUSE,
        note="министр",
        is_public_official=True,
        evidence=ev(),
    )
    pep = assess_pep(
        [pos("Директор", PositionCategory.PRIVATE_SECTOR, "KZ")],
        [relation],
        home_country="KZ",
        model=MODEL,
    )
    assert pep.category is PepCategory.FAMILY_OR_ASSOCIATE
    assert pep.clause is not None and "ст. 8" in pep.clause


def test_pep_not_confirmed_for_business_and_sport() -> None:
    positions = [
        pos("CEO", PositionCategory.PRIVATE_SECTOR, "US"),
        pos("Президент ФИДЕ", PositionCategory.NON_PROFIT, "KZ"),
    ]
    pep = assess_pep(positions, [], home_country="KZ", model=MODEL)
    assert pep.category is PepCategory.NOT_PEP
    assert "не подтверждён" in pep.rationale


def test_pep_undetermined() -> None:
    assert assess_pep([], [], home_country="KZ", model=MODEL).category is PepCategory.UNDETERMINED
    unknown = pos("Министр", PositionCategory.STATE_BODY, None)
    assert (
        assess_pep([unknown], [], home_country="KZ", model=MODEL).category
        is PepCategory.UNDETERMINED
    )


# ---------------------------------------------------------------- риск


def _inputs(**overrides: object) -> RiskInputs:
    values: dict[str, object] = {
        "pep": assess_pep([], [], home_country="KZ", model=MODEL),
        "identity": Identity(full_name="Тест", citizenship=["KZ"]),
        "positions": [],
        "relations": [],
        "companies": [],
        "adverse": [],
        "legal": [],
        "sanctions": SanctionsCheck(checked_at=NOW, lists=[]),
        "home_country": "KZ",
        "lists_loaded": True,
    }
    values.update(overrides)
    return RiskInputs(**values)  # type: ignore[arg-type]


def _levels(risk_inputs: RiskInputs) -> dict[FactorKey, RiskLevel]:
    risk = assess_risk(risk_inputs, model=MODEL, jurisdictions=JUR, now=NOW)
    return {f.key: f.level for f in risk.factors}


def test_clean_profile_is_low_or_medium() -> None:
    risk = assess_risk(_inputs(), model=MODEL, jurisdictions=JUR, now=NOW)
    levels = {f.key: f.level for f in risk.factors}
    assert levels[FactorKey.SANCTIONS] is RiskLevel.LOW
    assert levels[FactorKey.JURISDICTION] is RiskLevel.LOW
    assert levels[FactorKey.TRANSACTIONS] is RiskLevel.NO_DATA
    assert risk.level in {RiskLevel.LOW, RiskLevel.MEDIUM}
    assert risk.next_review > NOW.date()
    assert risk.method == MODEL.id


def test_foreign_pep_floor() -> None:
    minister = pos("Министр", PositionCategory.STATE_BODY, "BY", is_current=True)
    pep = assess_pep([minister], [], home_country="KZ", model=MODEL)
    risk = assess_risk(
        _inputs(pep=pep, positions=[minister]), model=MODEL, jurisdictions=JUR, now=NOW
    )
    assert risk.score >= 67
    assert risk.level is RiskLevel.HIGH
    assert any("ст. 8" in f or "8 Закона" in f for f in risk.floors)


def test_sanctions_match_floor_and_dob_conflict() -> None:
    hit = SanctionsCheck(checked_at=NOW, matches=[match("IVANOV PETR", dob_match=True)])
    risk = assess_risk(_inputs(sanctions=hit), model=MODEL, jurisdictions=JUR, now=NOW)
    assert risk.score >= 85
    conflict = SanctionsCheck(checked_at=NOW, matches=[match("IVANOV PETR", dob_match=False)])
    assert _levels(_inputs(sanctions=conflict))[FactorKey.SANCTIONS] is RiskLevel.MEDIUM


def test_media_sanctions_and_adverse() -> None:
    adverse = [
        AdverseItem(
            category=AdverseCategory.SANCTIONS,
            summary="Санкции Украины",
            severity=Severity.HIGH,
            evidence=ev(),
        ),
        AdverseItem(
            category=AdverseCategory.FRAUD,
            summary="Подозрения",
            severity=Severity.MEDIUM,
            evidence=ev("S2"),
        ),
    ]
    levels = _levels(_inputs(adverse=adverse))
    assert levels[FactorKey.SANCTIONS] is RiskLevel.HIGH
    assert levels[FactorKey.ADVERSE_MEDIA] is RiskLevel.MEDIUM


def test_jurisdiction_lists() -> None:
    assert (
        _levels(_inputs(identity=Identity(full_name="x", citizenship=["IR"])))[
            FactorKey.JURISDICTION
        ]
        is RiskLevel.HIGH
    )
    assert (
        _levels(_inputs(identity=Identity(full_name="x", citizenship=["VN"])))[
            FactorKey.JURISDICTION
        ]
        is RiskLevel.MEDIUM
    )
    assert (
        _levels(_inputs(identity=Identity(full_name="x", citizenship=["PA"])))[
            FactorKey.JURISDICTION
        ]
        is RiskLevel.MEDIUM
    )
    assert (
        _levels(_inputs(identity=Identity(full_name="x")))[FactorKey.JURISDICTION]
        is RiskLevel.NO_DATA
    )


def test_wealth_and_related() -> None:
    offshore = Company(name="Alfa Holdings", role=CompanyRole.OWNER, country="VG", evidence=ev())
    local = Company(name="Beta", role=CompanyRole.SHAREHOLDER, country="KZ", evidence=ev())
    assert _levels(_inputs(companies=[offshore]))[FactorKey.WEALTH] is RiskLevel.HIGH
    assert _levels(_inputs(companies=[local]))[FactorKey.WEALTH] is RiskLevel.MEDIUM
    assert _levels(_inputs(companies=[offshore]))[FactorKey.RELATED] is RiskLevel.HIGH
    official = Relation(
        name="Брат", relation=RelationKind.SIBLING, is_public_official=True, evidence=ev()
    )
    assert _levels(_inputs(relations=[official]))[FactorKey.RELATED] is RiskLevel.MEDIUM
    company_hit = match("BETA LLC", dob_match=None).model_copy(
        update={"query": "Beta", "entity_type": "entity"}
    )
    person_hit = match("ANNA IVANOVA", dob_match=None).model_copy(update={"query": "Анна Иванова"})
    related = SanctionsCheck(checked_at=NOW, related=[company_hit])
    assert _levels(_inputs(sanctions=related))[FactorKey.RELATED] is RiskLevel.HIGH
    related = SanctionsCheck(checked_at=NOW, related=[person_hit])
    assert _levels(_inputs(sanctions=related))[FactorKey.RELATED] is RiskLevel.MEDIUM


def test_legal_levels() -> None:
    case = LegalMatter(kind=LegalKind.CRIMINAL_CASE, summary="Дело", evidence=ev())
    probe = LegalMatter(kind=LegalKind.INVESTIGATION, summary="Проверка", evidence=ev())
    civil = LegalMatter(kind=LegalKind.CIVIL_CASE, summary="Иск", evidence=ev())
    assert _levels(_inputs(legal=[case]))[FactorKey.LEGAL] is RiskLevel.HIGH
    assert _levels(_inputs(legal=[probe]))[FactorKey.LEGAL] is RiskLevel.MEDIUM
    assert _levels(_inputs(legal=[civil]))[FactorKey.LEGAL] is RiskLevel.LOW
    assert _levels(_inputs(legal=[]))[FactorKey.LEGAL] is RiskLevel.NO_DATA


def test_lists_not_loaded() -> None:
    assert _levels(_inputs(lists_loaded=False))[FactorKey.SANCTIONS] is RiskLevel.NO_DATA


# ---------------------------------------------------------------- сведение фактов


def test_merge_facts_deduplicates_across_languages() -> None:
    facts = [
        SourceFacts(
            source_id="S1",
            about_subject="yes",
            positions=[
                pos(
                    "Президент ФИДЕ",
                    PositionCategory.NON_PROFIT,
                    "KZ",
                    organization="FIDE",
                    is_current=True,
                )
            ],
        ),
        SourceFacts(
            source_id="S2",
            about_subject="yes",
            positions=[
                Position(
                    title="President of FIDE",
                    organization="International Chess Federation (FIDE)",
                    category=PositionCategory.NON_PROFIT,
                    evidence=ev("S2"),
                )
            ],
        ),
        SourceFacts(
            source_id="S3",
            about_subject="no",
            positions=[pos("Министр", PositionCategory.STATE_BODY, "BY")],
        ),
    ]
    positions, *_ = merge_facts(facts)
    assert len(positions) == 1
    assert {e.source_id for e in positions[0].evidence} == {"S1", "S2"}


def test_identity_conflicts_and_votes() -> None:
    subject = Subject(full_name="Иванов Пётр")
    facts = [
        SourceFacts(
            source_id="S1",
            birth_date=FieldValue(value="1970-03-05", evidence=ev("S1")),
            birth_place=FieldValue(value="Минск", evidence=ev("S1")),
        ),
        SourceFacts(
            source_id="S2",
            birth_date=FieldValue(value="1970", evidence=ev("S2")),
            birth_place=FieldValue(value="Беларусь", evidence=ev("S2")),
        ),
        SourceFacts(
            source_id="S3",
            birth_date=FieldValue(value="1971-01-01", evidence=ev("S3")),
            citizenship=[FieldValue(value="BY", evidence=ev("S3"))],
        ),
    ]
    identity = build_identity(subject, "Petr Ivanov", facts)
    assert identity.birth_place is not None and identity.birth_place.value == "Минск"
    assert "birth_place" not in identity.conflicts  # страна не противоречит городу
    assert "birth_date" in identity.conflicts
    assert identity.citizenship == ["BY"]
    assert identity.latin_name == "Petr Ivanov"


def test_identity_prefers_analyst_birth_date() -> None:
    subject = Subject(full_name="Иванов Пётр", birth_date=date(1970, 3, 5), citizenship="BY")
    facts = [SourceFacts(source_id="S1", birth_date=FieldValue(value="1970", evidence=ev()))]
    identity = build_identity(subject, None, facts)
    assert identity.birth_date is not None and identity.birth_date.value == "1970-03-05"
    assert identity.conflicts == {}
    assert identity.citizenship == ["BY"]


def test_timeline_is_sorted_and_deduplicated() -> None:
    position = pos("Министр", PositionCategory.STATE_BODY, "BY", start="2019", end="2023")
    adverse = [
        AdverseItem(
            category=AdverseCategory.CORRUPTION, summary="Дело о взятке", date="2022", evidence=ev()
        )
    ]
    legal = [
        LegalMatter(
            kind=LegalKind.CRIMINAL_CASE, summary="Дело о взятке", date="2022", evidence=ev()
        )
    ]
    timeline = build_timeline([position], [], adverse, legal)
    assert [e.date for e in timeline] == ["2019", "2022", "2023"]


# ---------------------------------------------------------------- решение аналитика


def test_review_overrides_and_conclusion() -> None:
    from tests.sample import SUBJECT  # noqa: F401 — сценарий для полноты импорта

    minister = pos("Министр", PositionCategory.STATE_BODY, "BY", is_current=True)
    pep = assess_pep([minister], [], home_country="KZ", model=MODEL)
    risk = assess_risk(
        _inputs(pep=pep, positions=[minister]), model=MODEL, jurisdictions=JUR, now=NOW
    )
    text = write_conclusion(full_name="Иванов", headline="Министр", pep=pep, risk=risk)
    assert "Иванов — Министр." in text
    assert "пункта 1 статьи 8" in text

    from ipdl.analysis.model import Portrait, RunStats, Source, SourceKind

    portrait = Portrait(
        subject=Subject(full_name="Иванов Пётр"),
        identity=Identity(full_name="Иванов Пётр", citizenship=["BY"]),
        pep=pep,
        risk=risk,
        positions=[minister],
        sanctions=SanctionsCheck(checked_at=NOW, lists=[]),
        sources=[
            Source(
                id="S1",
                url="https://x",
                title="x",
                domain="x",
                kind=SourceKind.MEDIA,
                retrieved_at=NOW,
            )
        ],
        conclusion=text,
        stats=RunStats(),
    )
    review = Review(
        pep_category=PepCategory.NOT_PEP,
        pep_comment="Должность почётная, не является публичной функцией",
        factors={
            FactorKey.TRANSACTIONS: FactorOverride(
                level=RiskLevel.HIGH, comment="Три СПО за 2026 год"
            )
        },
        sources={"S1": Verification.CONFIRMED},
        conclusion="Итог аналитика",
    )
    result = apply_review(portrait, review, model=MODEL, jurisdictions=JUR, home_country="KZ")
    assert result.pep.category is PepCategory.NOT_PEP
    assert result.pep.rationale.startswith("Решение аналитика")
    transactions = next(f for f in result.risk.factors if f.key is FactorKey.TRANSACTIONS)
    assert transactions.level is RiskLevel.HIGH
    assert transactions.auto_level is RiskLevel.NO_DATA
    assert transactions.overridden
    assert result.sources[0].verification is Verification.CONFIRMED
    assert result.conclusion == "Итог аналитика"
    assert portrait.pep.category is PepCategory.FOREIGN  # исходный портрет не изменён
    assert (
        apply_review(portrait, None, model=MODEL, jurisdictions=JUR, home_country="KZ") is portrait
    )


def test_birth_place_spelling_variants_are_not_conflicts() -> None:
    facts = [
        SourceFacts(
            source_id="S1",
            birth_place=FieldValue(value="д. Солтанишки, Вороновский район", evidence=ev("S1")),
        ),
        SourceFacts(
            source_id="S2", birth_place=FieldValue(value="деревня Солтанишки", evidence=ev("S2"))
        ),
        SourceFacts(source_id="S3", birth_place=FieldValue(value="Солтанишки", evidence=ev("S3"))),
    ]
    identity = build_identity(Subject(full_name="Тест Тестов"), None, facts)
    assert "birth_place" not in identity.conflicts
    facts.append(
        SourceFacts(source_id="S4", birth_place=FieldValue(value="Гродно", evidence=ev("S4")))
    )
    assert "birth_place" in build_identity(Subject(full_name="Тест Тестов"), None, facts).conflicts


def test_head_of_state_ranks_first() -> None:
    facts = [
        SourceFacts(
            source_id="S1",
            about_subject="yes",
            positions=[
                pos("Заместитель министра", PositionCategory.STATE_BODY, "UZ", is_current=False),
                pos(
                    "Президент Республики Узбекистан",
                    PositionCategory.STATE_BODY,
                    "UZ",
                    is_current=True,
                ),
                pos("Хоким области", PositionCategory.STATE_BODY, "UZ", is_current=False),
            ],
        )
    ]
    positions, *_ = merge_facts(facts)
    assert positions[0].title == "Президент Республики Узбекистан"
