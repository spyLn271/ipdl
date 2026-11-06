"""Страны: приведение названий («Казахстан», «Kazakhstan», «KZ») к ISO 3166-1 alpha-2.

Названия берутся из CLDR (Babel) на русском, казахском и английском — те же, что в
интерфейсе, — плюс распространённые варианты из санкционных списков и СМИ.
"""

from __future__ import annotations

import re
from functools import cache

from babel import Locale

_LOCALES = ("ru", "kk", "en")
_ALIASES = {
    "россия": "RU",
    "рф": "RU",
    "russia": "RU",
    "russian federation": "RU",
    "сша": "US",
    "usa": "US",
    "united states of america": "US",
    "uk": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "великобритания": "GB",
    "англия": "GB",
    "оаэ": "AE",
    "uae": "AE",
    "кнр": "CN",
    "китай": "CN",
    "кндр": "KP",
    "north korea": "KP",
    "dprk": "KP",
    "democratic people's republic of korea": "KP",
    "south korea": "KR",
    "iran (islamic republic of)": "IR",
    "syrian arab republic": "SY",
    "viet nam": "VN",
    "lao pdr": "LA",
    "lao people's democratic republic": "LA",
    "democratic republic of the congo": "CD",
    "congo, democratic republic of the": "CD",
    "côte d'ivoire": "CI",
    "cote d'ivoire": "CI",
    "virgin islands (uk)": "VG",
    "british virgin islands": "VG",
    "бви": "VG",
    "bosnia and herzegovina": "BA",
    "türkiye": "TR",
    "turkey": "TR",
    "republic of moldova": "MD",
    "belarus": "BY",
    "беларусь": "BY",
    "белоруссия": "BY",
    "кипр": "CY",
    "cyprus": "CY",
}
_SPACES = re.compile(r"\s+")


def _key(value: str) -> str:
    return _SPACES.sub(" ", value.strip().casefold().replace("ё", "е"))


@cache
def _index() -> dict[str, str]:
    index: dict[str, str] = {}
    for code in _LOCALES:
        for territory, name in Locale.parse(code).territories.items():
            if len(territory) == 2 and territory.isalpha():
                index.setdefault(_key(name), territory)
    index.update(_ALIASES)
    return index


def to_iso2(value: str | None) -> str | None:
    """«Казахстан» → «KZ»; неизвестное название → ``None``."""
    if not value:
        return None
    text = value.strip()
    if len(text) == 2 and text.isalpha():
        code = text.upper()
        return code if code in Locale.parse("en").territories else None
    return _index().get(_key(text))


def country_name(code: str | None, locale: str = "ru") -> str | None:
    if not code:
        return None
    name = Locale.parse(locale).territories.get(code.upper())
    return str(name) if name else code.upper()
