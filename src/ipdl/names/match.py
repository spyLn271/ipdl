"""Нечёткое сравнение имён без учёта порядка слов, алфавита и способа транслитерации.

Имя сводится к «скелету»: латиница по ICAO, нижний регистр, без диакритики и с
выравниванием типичных расхождений романизации (``Yuriy``/``Iurii``/``Juri``,
``Aleksandr``/``Alexander``, ``Shchukin``/``Schukin``). Затем токены сопоставляются
попарно (каждый токен кандидата — не больше одного раза), отчество может отсутствовать.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from functools import cache

from rapidfuzz.fuzz import ratio

from ipdl.names.translit import strip_accents, transliterate

_NON_LETTERS = re.compile(r"[^a-z]+")
_DOUBLE = re.compile(r"(.)\1+")
# Порядок важен: сначала длинные сочетания
_FOLDS: tuple[tuple[str, str], ...] = (
    ("shch", "sh"),
    ("sch", "sh"),
    ("tch", "ch"),
    ("dzh", "j"),
    ("dj", "j"),
    ("zh", "j"),
    ("kh", "h"),
    ("ph", "f"),
    ("ck", "k"),
    ("x", "ks"),
    ("w", "v"),
    ("ou", "u"),
    ("y", "i"),
    ("iu", "u"),
    ("ia", "a"),
    ("ie", "e"),
)
_HONORIFICS = frozenset({"mr", "mrs", "ms", "dr", "prof", "gen", "general", "col", "sir"})
# Организационно-правовые формы и общие слова в названиях компаний: по ним «Freedom Finance
# Bank» совпал бы с любым «… Finance Bank». Сравниваются в виде «скелетов» (см. fold).
_ENTITY_STOPWORDS_RAW = (
    "ао оао зао пао тоо ооо ип тов пат ag sa bv nv llc llp ltd limited inc corp corporation "
    "co company plc gmbh jsc ojsc cjsc pjsc group holding holdings bank finance financial "
    "investment investments invest capital insurance international trading trade services "
    "service the of and fund partners global management компания корпорация группа холдинг "
    "банк финанс финансы финансовая инвест инвестиции инвестиционная капитал страховая "
    "страхование международный международная торговый торговая фонд партнёрс казахстан "
    "kazakhstan россия russia и"
)


def fold(name: str) -> str:
    """Скелет имени для сравнения: ``"Юрий Щукин"`` → ``"uri shukin"``."""
    text = transliterate(strip_accents(name), "icao").lower()
    text = _DOUBLE.sub(r"\1", _NON_LETTERS.sub(" ", text))
    for old, new in _FOLDS:
        # удвоения схлопываем после каждой замены: «Mariya» → «mariia» → «maria» → «mara»
        text = _DOUBLE.sub(r"\1", text.replace(old, new))
    return " ".join(text.split())


def tokens(name: str) -> list[str]:
    return [t for t in fold(name).split() if len(t) > 1 and t not in _HONORIFICS]


@cache
def _entity_stopwords() -> frozenset[str]:
    return frozenset(fold(word) for word in _ENTITY_STOPWORDS_RAW.split())


def entity_tokens(name: str) -> list[str]:
    """Отличительные слова названия компании (без «АО», «Bank», «Holding»…)."""
    stop = _entity_stopwords()
    return [t for t in tokens(name) if t not in stop]


def entity_similarity(query: Sequence[str], candidate: Sequence[str]) -> float:
    """Сходство названий компаний: каждое отличительное слово запроса должно найтись.

    В отличие от имён людей (где отчество может отсутствовать), здесь учитываются все
    отличительные слова запроса — иначе «Freedom Finance» совпадёт с «Rost Finance».
    """
    if not query or not candidate:
        return 0.0
    scores = [max(ratio(q, c) for c in candidate) for q in query]
    return round(sum(scores) / len(scores), 1)


def similarity(query: Sequence[str], candidate: Sequence[str]) -> float:
    """Сходство 0–100 двух имён, разбитых на токены функцией :func:`tokens`.

    Учитываются ``k = min(len(query), len(candidate), 3)`` лучших пар токенов: так
    «Тимур Турлов» и «Timur Ruslanovich TURLOV» дают 100. Однословное имя против
    многословного штрафуется — фамилия сама по себе не совпадение.
    """
    if not query or not candidate:
        return 0.0
    pairs = sorted(
        ((ratio(q, c), qi, ci) for qi, q in enumerate(query) for ci, c in enumerate(candidate)),
        reverse=True,
    )
    used_q: set[int] = set()
    used_c: set[int] = set()
    best: list[float] = []
    for score, qi, ci in pairs:
        if qi in used_q or ci in used_c:
            continue
        used_q.add(qi)
        used_c.add(ci)
        best.append(score)
    k = min(len(query), len(candidate), 3)
    value = sum(best[:k]) / k
    if k == 1 and max(len(query), len(candidate)) > 1:
        value *= 0.7
    return round(value, 1)


def name_similarity(a: str, b: str) -> float:
    return similarity(tokens(a), tokens(b))
