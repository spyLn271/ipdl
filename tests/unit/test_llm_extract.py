from __future__ import annotations

from typing import Any

import pytest

from ipdl.analysis.model import PositionCategory, RelationKind
from ipdl.llm.extract import (
    FACTS_SCHEMA,
    FactExtractor,
    check_category,
    normalize_date,
    parse_facts,
    quote_in_text,
    relation_from_note,
)
from ipdl.llm.templates import load_prompt
from tests.fakes import FakeLLM

TEXT = (
    "Пётр Сергеевич Иванов (род. 5 марта 1970 года в Минске) — с 2019 года министр финансов "
    "Республики Беларусь. Его жена Анна Иванова владеет компанией Alfa Holdings Ltd. "
    "В 2023 году Украина ввела санкции против Иванова. Он входит в рейтинг Forbes вместе с "
    "Сергеем Петровым (№ 17 рейтинга). Президент Международной шахматной федерации (FIDE)."
)


def _answer(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "about_subject": "yes",
        "birth_date": {"value": "", "quote": ""},
        "birth_place": {"value": "", "quote": ""},
        "citizenship": [],
        "positions": [],
        "relations": [],
        "companies": [],
        "adverse": [],
        "legal": [],
        "events": [],
    }
    base.update(overrides)
    return base


def test_quote_matching_tolerates_typography() -> None:
    assert quote_in_text("с 2019 года министр финансов", TEXT)
    assert quote_in_text(
        "Его жена Анна Иванова владеет компанией «Alfa Holdings Ltd»",
        TEXT.replace("Alfa Holdings Ltd", '"Alfa Holdings Ltd"'),
    )
    assert not quote_in_text("министр обороны Республики Беларусь", TEXT)
    assert not quote_in_text("коротко", TEXT)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2019", "2019"),
        ("2019-05", "2019-05"),
        ("2019-05-14", "2019-05-14"),
        ("май 2019", "2019"),
        ("5 марта 1970", "1970-03-05"),
        ("13 November 1987", "1987-11-13"),
        ("November 13, 1987", "1987-11-13"),
        ("13.11.1987", "1987-11-13"),
        ("5 наурыз 1970", "1970-03-05"),
        ("2019-13", "2019"),
        ("", None),
        ("давно", None),
    ],
)
def test_normalize_date(raw: str, expected: str | None) -> None:
    assert normalize_date(raw) == expected


def test_facts_without_supported_quotes_are_dropped() -> None:
    facts = parse_facts(
        _answer(
            birth_date={"value": "5 марта 1970", "quote": "род. 5 марта 1970 года в Минске"},
            positions=[
                {
                    "title": "Министр финансов",
                    "organization": "Минфин",
                    "country": "Беларусь",
                    "start": "2019",
                    "end": "",
                    "current": "yes",
                    "category": "state_body",
                    "quote": "с 2019 года министр финансов Республики Беларусь",
                },
                {
                    "title": "Министр обороны",
                    "organization": "",
                    "country": "BY",
                    "start": "",
                    "end": "",
                    "current": "yes",
                    "category": "state_body",
                    "quote": "назначен министром обороны",
                },
                {
                    "title": "",
                    "organization": "",
                    "country": "",
                    "start": "",
                    "end": "",
                    "current": "unknown",
                    "category": "other",
                    "quote": "",
                },
            ],
        ),
        source_id="S1",
        text=TEXT,
    )
    assert facts.birth_date is not None
    assert facts.birth_date.value == "1970-03-05"
    assert [p.title for p in facts.positions] == ["Министр финансов"]
    position = facts.positions[0]
    assert position.country == "BY"
    assert position.is_current is True
    assert position.evidence[0].source_id == "S1"
    assert facts.dropped == 1


def test_birth_date_year_fallback() -> None:
    facts = parse_facts(
        _answer(birth_date={"value": "1970", "quote": "род. 5 марта 1970 года"}),
        source_id="S1",
        text=TEXT,
    )
    assert facts.birth_date is not None
    assert facts.birth_date.value == "1970"


def test_other_person_is_ignored() -> None:
    facts = parse_facts(
        _answer(
            about_subject="no",
            positions=[{"title": "Министр", "quote": "с 2019 года министр финансов"}],
        ),
        source_id="S1",
        text=TEXT,
    )
    assert facts.total == 0


def test_relation_guards() -> None:
    facts = parse_facts(
        _answer(
            relations=[
                {
                    "name": "Анна Иванова",
                    "relation": "spouse",
                    "note": "",
                    "public_official": "no",
                    "quote": "Его жена Анна Иванова владеет компанией",
                },
                {
                    "name": "Сергей Петров",
                    "relation": "other_relative",
                    "note": "№ 17 рейтинга",
                    "public_official": "no",
                    "quote": "вместе с Сергеем Петровым (№ 17 рейтинга)",
                },
                {
                    "name": "Три сына",
                    "relation": "child",
                    "note": "",
                    "public_official": "no",
                    "quote": "Его жена Анна Иванова владеет компанией",
                },
            ]
        ),
        source_id="S1",
        text=TEXT,
    )
    assert [(r.name, r.relation) for r in facts.relations] == [
        ("Анна Иванова", RelationKind.SPOUSE)
    ]


def test_sanctions_are_not_legal_cases() -> None:
    facts = parse_facts(
        _answer(
            adverse=[
                {
                    "category": "sanctions",
                    "summary": "Украина ввела санкции",
                    "date": "2023",
                    "severity": "high",
                    "quote": "В 2023 году Украина ввела санкции против Иванова",
                }
            ],
            legal=[
                {
                    "kind": "criminal_case",
                    "summary": "Санкции Украины",
                    "jurisdiction": "UA",
                    "status": "",
                    "date": "2023",
                    "quote": "В 2023 году Украина ввела санкции против Иванова",
                }
            ],
        ),
        source_id="S2",
        text=TEXT,
    )
    assert len(facts.adverse) == 1
    assert facts.legal == []


def test_bad_enum_values_fall_back() -> None:
    facts = parse_facts(
        _answer(
            companies=[
                {
                    "name": "Alfa Holdings Ltd",
                    "role": "boss",
                    "share_percent": "25,5%",
                    "country": "Кипр",
                    "quote": "владеет компанией Alfa Holdings Ltd",
                }
            ]
        ),
        source_id="S1",
        text=TEXT,
    )
    company = facts.companies[0]
    assert company.role.value == "other"
    assert company.share_percent == 25.5
    assert company.country == "CY"


@pytest.mark.parametrize(
    ("title", "organization", "expected"),
    [
        ("Президент", "Международная шахматная федерация (FIDE)", PositionCategory.NON_PROFIT),
        ("President", "International Olympic Committee", PositionCategory.NON_PROFIT),
        ("Managing Director", "International Monetary Fund", PositionCategory.INTERNATIONAL_ORG),
        ("Член коллегии", "Евразийская экономическая комиссия", PositionCategory.INTERNATIONAL_ORG),
        (
            "Председатель Консультативного комитета",
            "Глобальный договор ООН",
            PositionCategory.NON_PROFIT,
        ),
        ("Director", "Some Treaty Organisation", PositionCategory.INTERNATIONAL_ORG),
    ],
)
def test_international_org_guard(title: str, organization: str, expected: PositionCategory) -> None:
    assert check_category(PositionCategory.INTERNATIONAL_ORG, title, organization) is expected


def test_guard_only_touches_international_orgs() -> None:
    assert (
        check_category(PositionCategory.STATE_BODY, "Президент федерации", None)
        is PositionCategory.STATE_BODY
    )


def test_schema_and_prompt() -> None:
    assert FACTS_SCHEMA["additionalProperties"] is False
    assert set(FACTS_SCHEMA["required"]) >= {"about_subject", "positions", "adverse"}
    prompt = load_prompt("extract.facts")
    assert prompt.version != "0"
    system, user = prompt.render(
        name="Иванов", latin="Ivanov", extra="", title="T", domain="d", text="текст"
    )
    assert "AML/KYC" in system
    assert "Иванов" in user and "текст" in user


async def test_extractor_uses_llm() -> None:
    llm = FakeLLM(
        {
            "(example.org)": _answer(
                events=[
                    {"date": "2019", "summary": "Назначен", "quote": "с 2019 года министр финансов"}
                ]
            )
        }
    )
    facts = await FactExtractor(llm).extract(
        source_id="S9", text=TEXT, title="T", domain="example.org", name="Иванов Пётр", latin=None
    )
    assert facts.events[0].date == "2019"
    assert "Иванов Пётр" in llm.calls[0]


@pytest.mark.parametrize(
    ("category", "title", "organization", "expected"),
    [
        (
            PositionCategory.STATE_BODY,
            "Председатель",
            "Национальный олимпийский комитет Узбекистана",
            PositionCategory.NON_PROFIT,
        ),
        (
            PositionCategory.PUBLIC_FUNCTION,
            "Президент",
            "Федерация шахмат",
            PositionCategory.NON_PROFIT,
        ),
        (PositionCategory.STATE_BODY, "Член", "Совет Федерации", PositionCategory.STATE_BODY),
        (
            PositionCategory.STATE_BODY,
            "Министр финансов",
            "Правительство Российской Федерации",
            PositionCategory.STATE_BODY,
        ),
    ],
)
def test_sport_and_charity_are_not_state_bodies(
    category: PositionCategory, title: str, organization: str, expected: PositionCategory
) -> None:
    assert check_category(category, title, organization) is expected


@pytest.mark.parametrize(
    ("relation", "note", "expected"),
    [
        (RelationKind.SPOUSE, "father", RelationKind.PARENT),
        (RelationKind.ASSOCIATE, "его сын", RelationKind.CHILD),
        (RelationKind.CHILD, "сын и брат", RelationKind.CHILD),  # неоднозначно — как есть
        (RelationKind.SPOUSE, None, RelationKind.SPOUSE),
    ],
)
def test_relation_kind_follows_note(
    relation: RelationKind, note: str | None, expected: RelationKind
) -> None:
    assert relation_from_note(relation, note) is expected
