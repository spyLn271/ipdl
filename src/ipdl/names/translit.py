"""Транслитерация имён (русский, казахский, украинский алфавиты → латиница).

Две схемы:

* ``icao`` — ICAO Doc 9303 (как в загранпаспортах): «Юрий» → «Iurii», «Щукин» → «Shchukin».
  Ей пользуемся для сопоставления с санкционными списками.
* ``popular`` — привычное написание в СМИ (близко к BGN/PCGN): «Юрий» → «Yuriy»,
  «Турлов Тимур» → «Turlov Timur». Им строим поисковые запросы на латинице.
"""

from __future__ import annotations

import unicodedata
from typing import Literal

type Scheme = Literal["icao", "popular"]

_ICAO: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "ie", "ы": "y", "ь": "", "э": "e", "ю": "iu",
    "я": "ia",
    # казахский
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i",
    # украинский
    "є": "ie", "ї": "i", "ґ": "g",
}  # fmt: skip

_POPULAR: dict[str, str] = {
    **_ICAO,
    "ё": "yo",
    "й": "y",
    "ъ": "",
    "ю": "yu",
    "я": "ya",
    "є": "ye",
    "ї": "yi",
}

_TABLES: dict[str, dict[str, str]] = {"icao": _ICAO, "popular": _POPULAR}


def has_cyrillic(text: str) -> bool:
    return any("CYRILLIC" in unicodedata.name(ch, "") for ch in text)


def transliterate(text: str, scheme: Scheme = "icao") -> str:
    """Транслитерировать кириллицу; латиница и прочие символы остаются как есть."""
    table = _TABLES[scheme]
    out: list[str] = []
    for index, ch in enumerate(text):
        lower = ch.lower()
        latin = table.get(lower)
        if latin is None:
            out.append(ch)
            continue
        if scheme == "popular" and lower == "е" and index > 0 and text[index - 1].lower() in "ьъ":
            latin = "ye"  # «Григорьев» → «Grigoryev»
        if ch.isupper() and latin:
            following = text[index + 1] if index + 1 < len(text) else ""
            latin = latin.upper() if following.isupper() else latin[0].upper() + latin[1:]
        out.append(latin)
    return "".join(out)


def strip_accents(text: str) -> str:
    """«Müller» → «Muller», «Ştefan» → «Stefan»; кириллица («й», «ё») не затрагивается."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", text):
        if "LATIN" in unicodedata.name(ch, ""):
            decomposed = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
        else:
            out.append(ch)
    return "".join(out)
