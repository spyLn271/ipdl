from __future__ import annotations

from pathlib import Path

import pytest

from ipdl.sanctions.parsers import (
    SanctionsParseError,
    normalize_date,
    parse,
    published_at,
)
from tests.conftest import FIXTURES

LISTS = FIXTURES / "sanctions"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10 Dec 1948", "1948-12-10"),
        ("Dec 1948", "1948-12"),
        ("circa 1948", "1948"),
        ("13/11/1987", "1987-11-13"),
        ("dd/mm/1945", "1945"),
        ("dd/11/1945", "1945-11"),
        ("1978-04-28", "1978-04-28"),
        ("2026-10-26T23:00:02.307Z", "2026-10-26"),
        ("between 1960 and 1962", "1960"),
        ("", None),
        ("unknown", None),
    ],
)
def test_normalize_date(raw: str, expected: str | None) -> None:
    assert normalize_date(raw) == expected


def test_un() -> None:
    entries = list(parse("un", LISTS / "un.xml"))
    person = entries[0]
    assert person.ref == "TSi.001"
    assert person.entity_type == "person"
    assert person.primary_name == "PETR SERGEEVICH IVANOV"
    assert "Pyotr Ivanov" in person.names
    assert person.birth_dates == ["1970-03-05"]
    assert person.nationalities == ["Belarus"]
    assert person.listed_on == "2014-03-21"
    assert entries[1].birth_dates == ["1960", "1961", "1962"]
    entity = entries[2]
    assert entity.entity_type == "entity"
    assert entity.names == ["NORTHWIND TRADING COMPANY", "Northwind LLC"]
    assert published_at("un", LISTS / "un.xml") == "2026-10-26"


def test_ofac() -> None:
    person, bank = list(parse("ofac_sdn", LISTS / "ofac.xml"))
    assert person.primary_name == "Viktar Uladzimiravich TESTMAN"
    assert "Viktor Vladimirovich TESTMAN" in person.names
    assert person.birth_dates == ["1958-05-26"]
    assert person.programs == ["BELARUS"]
    assert bank.entity_type == "entity"
    assert published_at("ofac_sdn", LISTS / "ofac.xml") == "2026-10-21"


def test_eu() -> None:
    person, company = list(parse("eu_fsf", LISTS / "eu.xml"))
    assert person.ref == "EU.1.1"
    assert "Виктор Владимирович ТЕСТМАН" in person.names
    assert person.nationalities == ["BY"]
    assert person.listed_on == "2011-06-21"
    assert company.entity_type == "entity"
    assert company.nationalities == []
    assert published_at("eu_fsf", LISTS / "eu.xml") == "2026-10-23"


def test_uk() -> None:
    (person,) = list(parse("uk_fcdo", LISTS / "uk.xml"))
    assert person.primary_name == "Viktar Uladzimiravich TESTMAN"
    assert "Віктар Уладзіміравіч Тэстман" in person.names
    assert person.birth_dates == ["1958-05-26", "1957"]
    assert person.listed_on == "2020-12-17"
    assert published_at("uk_fcdo", LISTS / "uk.xml") == "2026-10-27"


def test_unknown_format() -> None:
    with pytest.raises(SanctionsParseError):
        parse("nope", LISTS / "un.xml")


def test_broken_xml(tmp_path: Path) -> None:
    broken = tmp_path / "broken.xml"
    broken.write_text("<CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL>", encoding="utf-8")
    with pytest.raises(SanctionsParseError):
        list(parse("un", broken))


def test_external_entities_are_not_resolved(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET", encoding="utf-8")
    xml = tmp_path / "xxe.xml"
    xml.write_text(
        f'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file://{secret}">]>'
        "<CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL><REFERENCE_NUMBER>X</REFERENCE_NUMBER>"
        "<FIRST_NAME>&xxe;</FIRST_NAME></INDIVIDUAL></INDIVIDUALS></CONSOLIDATED_LIST>",
        encoding="utf-8",
    )
    entries = list(parse("un", xml))
    assert all("TOPSECRET" not in name for e in entries for name in e.names)
