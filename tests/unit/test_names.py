from __future__ import annotations

import pytest

from ipdl.names.match import entity_similarity, entity_tokens, fold, name_similarity, tokens
from ipdl.names.translit import has_cyrillic, strip_accents, transliterate


@pytest.mark.parametrize(
    ("text", "scheme", "expected"),
    [
        ("Юрий Щукин", "icao", "Iurii Shchukin"),
        ("Юрий Щукин", "popular", "Yuriy Shchukin"),
        ("Тимур Турлов", "popular", "Timur Turlov"),
        ("Григорьев", "popular", "Grigoryev"),
        ("Әлихан Қасымұлы", "icao", "Alikhan Kasymuly"),
        ("ТОО", "icao", "TOO"),
        ("Smith", "icao", "Smith"),
    ],
)
def test_transliterate(text: str, scheme: str, expected: str) -> None:
    assert transliterate(text, scheme) == expected  # type: ignore[arg-type]


def test_strip_accents_keeps_cyrillic_letters() -> None:
    assert strip_accents("Müller Ştefan") == "Muller Stefan"
    assert strip_accents("Йосиф Ёлкин") == "Йосиф Ёлкин"


def test_has_cyrillic() -> None:
    assert has_cyrillic("Иван Smith")
    assert not has_cyrillic("John Smith")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Юрий Щукин", "Iurii Shchukin"),
        ("Юрий Щукин", "Yuriy Schukin"),
        ("Mariya", "Мария"),
        ("Aleksandr", "Alexandr"),
    ],
)
def test_fold_aligns_romanizations(a: str, b: str) -> None:
    assert fold(a) == fold(b)


def test_close_romanizations_are_similar() -> None:
    assert name_similarity("Alexander Petrov", "Aleksandr Petrov") >= 90


def test_similarity_ignores_order_and_missing_patronymic() -> None:
    assert name_similarity("Тимур Турлов", "TURLOV Timur Ruslanovich") == 100
    assert name_similarity("Шейман Виктор Владимирович", "Viktar Uladzimiravich SHEIMAN") >= 88


def test_similarity_rejects_different_people() -> None:
    assert name_similarity("Тимур Турлов", "Timur Bekmambetov") < 88
    assert name_similarity("Тимур Турлов", "Abu Ali") < 50


def test_single_token_is_penalized() -> None:
    assert name_similarity("Тимур Турлов", "TURLOV") < 88


def test_tokens_drop_honorifics() -> None:
    assert tokens("Dr. John Smith") == ["john", "smith"]


def test_entity_matching_ignores_generic_words() -> None:
    assert entity_tokens("Freedom Finance Bank JSC") == ["fredom"]
    assert (
        entity_similarity(entity_tokens("Freedom Finance Bank"), entity_tokens("BANK ROSTFINANCE"))
        < 50
    )
    assert (
        entity_similarity(entity_tokens("АО «Фридом Финанс»"), entity_tokens("Freedom Finance"))
        >= 80
    )
    assert entity_similarity([], ["x"]) == 0
