"""Извлечение фактов о лице из текста одного источника с помощью локальной LLM.

Защита от «галлюцинаций» маленьких моделей:

* ответ строго по JSON-схеме (грамматика Ollama), значения — из перечислений;
* у каждого факта — дословная цитата; цитата ищется в тексте источника (после нормализации
  пробелов, кавычек и тире), допускается расхождение в пару символов — иначе факт отброшен;
* «about_subject: no» (однофамилец) — отбрасываются все факты источника;
* даты и страны приводятся к ISO, неразборчивые значения обнуляются.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from rapidfuzz.fuzz import partial_ratio

from ipdl.analysis.model import (
    AdverseCategory,
    AdverseItem,
    Company,
    CompanyRole,
    Evidence,
    FieldValue,
    LegalKind,
    LegalMatter,
    Position,
    PositionCategory,
    Relation,
    RelationKind,
    Severity,
    TimelineEvent,
)
from ipdl.geo import to_iso2
from ipdl.llm.client import LLMClient
from ipdl.llm.templates import load_prompt
from ipdl.logs import get_logger

log = get_logger(__name__)

PROMPT_NAME = "extract.facts"
_QUOTE_MIN_RATIO = 92
_QUOTES = str.maketrans({"«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "’": "'", "‘": "'"})
_DASHES = re.compile(r"[‐-―−]")
_WS = re.compile(r"\s+")
_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$")
_YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_DMY = re.compile(
    r"\b(\d{1,2})[.\s]+([a-zа-яёәғқңөұүһі]+|\d{1,2})[.\s,]+(1[89]\d{2}|20\d{2})\b", re.IGNORECASE
)
_MDY = re.compile(r"\b([a-z]+)\s+(\d{1,2}),?\s+(1[89]\d{2}|20\d{2})\b", re.IGNORECASE)
# Основы названий месяцев: русский (в т. ч. родительный падеж), казахский, английский
_MONTH_STEMS = (
    ("янв", "қаңтар", "jan"),
    ("фев", "ақпан", "feb"),
    ("мар", "наурыз", "mar"),
    ("апр", "сәуір", "apr"),
    ("мая", "май", "мамыр", "may"),
    ("июн", "маусым", "jun"),
    ("июл", "шілде", "jul"),
    ("авг", "тамыз", "aug"),
    ("сен", "қыркүйек", "sep"),
    ("окт", "қазан", "oct"),
    ("ноя", "қараша", "nov"),
    ("дек", "желтоқсан", "dec"),
)


def _month(word: str) -> int | None:
    if word.isdigit():
        number = int(word)
        return number if 1 <= number <= 12 else None
    lowered = word.lower()
    for index, stems in enumerate(_MONTH_STEMS, start=1):
        if any(lowered.startswith(stem) for stem in stems):
            return index
    return None


_YES_NO = ["yes", "no", "unknown"]

# Межгосударственные организации (абз. 8 пп. 3-3) ст. 1): созданы государствами по договору
_INTERGOVERNMENTAL = re.compile(
    r"\b(оон|united nations|undp|unicef|unesco|unhcr|unctad|unodc|юнеско|юнисеф|"
    r"воз\b|who\b|мвф|imf\b|"
    r"международн\w* валютн\w* фонд|international monetary fund|всемирн\w* банк|world bank|"
    r"ibrd|мбрр|ifc\b|ебрр|ebrd|азиатск\w* банк развития|asian development bank|adb\b|aiib|"
    r"исламск\w* банк развития|islamic development bank|еабр|eurasian development bank|"
    r"еаэс|eaeu|евразийск\w* экономическ\w*|eurasian economic|снг\b|cis\b|одкб|csto|шос\b|"
    r"\bsco\b|шанхайск\w* организаци|обсе|osce|нато|nato|european commission|еврокомисси|"
    r"европейск\w* (комисси|парламент|совет|центральн\w* банк)|european (parliament|council|"
    r"central bank)|совет европы|council of europe|оэср|oecd|вто\b|wto\b|интерпол|interpol|"
    r"опек|opec|african union|африканск\w* союз|asean|асеан|лига арабских|arab league|"
    r"организаци\w* исламского сотрудничества|\boic\b|свмда|cica|организаци\w* тюркских|"
    r"turkic states|магатэ|iaea|икао|icao|\bilo\b|\bмот\b|\bfao\b|\bwipo\b|\bitu\b)",
    re.IGNORECASE,
)
# Инициативы и совещательные органы при ООН и т. п. — не должности в межгос. организации
_ADVISORY = re.compile(
    r"(global compact|глобальн\w* договор|консультативн|advisory|попечительск|"
    r"goodwill ambassador|посол доброй воли|почётн|honorary)",
    re.IGNORECASE,
)
# Спортивные федерации, фонды, ассоциации — НКО, даже если они «международные»
_NON_GOVERNMENTAL = re.compile(
    r"(федерац|federation|\bfide\b|фиде|олимпи|olympic|\bмок\b|\bioc\b|fifa|фифа|uefa|"
    r"уефа|ассоциаци|association|благотворит|charit|foundation|клуб|\bclub\b|университет|"
    r"university|академи|academy)",
    re.IGNORECASE,
)


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _array(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": _obj(properties)}


_S = {"type": "string"}


def _enum(values: list[str]) -> dict[str, Any]:
    return {"type": "string", "enum": values}


FACTS_SCHEMA: dict[str, Any] = _obj(
    {
        "about_subject": _enum(["yes", "no", "unclear"]),
        "birth_date": _obj({"value": _S, "quote": _S}),
        "birth_place": _obj({"value": _S, "quote": _S}),
        "citizenship": _array({"country": _S, "quote": _S}),
        "positions": _array(
            {
                "title": _S,
                "organization": _S,
                "country": _S,
                "start": _S,
                "end": _S,
                "current": _enum(_YES_NO),
                "category": _enum([c.value for c in PositionCategory]),
                "quote": _S,
            }
        ),
        "relations": _array(
            {
                "name": _S,
                "relation": _enum([r.value for r in RelationKind]),
                "note": _S,
                "public_official": _enum(_YES_NO),
                "quote": _S,
            }
        ),
        "companies": _array(
            {
                "name": _S,
                "role": _enum([r.value for r in CompanyRole]),
                "share_percent": _S,
                "country": _S,
                "quote": _S,
            }
        ),
        "adverse": _array(
            {
                "category": _enum([c.value for c in AdverseCategory]),
                "summary": _S,
                "date": _S,
                "severity": _enum([s.value for s in Severity]),
                "quote": _S,
            }
        ),
        "legal": _array(
            {
                "kind": _enum([k.value for k in LegalKind]),
                "summary": _S,
                "jurisdiction": _S,
                "status": _S,
                "date": _S,
                "quote": _S,
            }
        ),
        "events": _array({"date": _S, "summary": _S, "quote": _S}),
    }
)


@dataclass(slots=True)
class SourceFacts:
    source_id: str
    about_subject: str = "unclear"
    birth_date: FieldValue | None = None
    birth_place: FieldValue | None = None
    citizenship: list[FieldValue] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    companies: list[Company] = field(default_factory=list)
    adverse: list[AdverseItem] = field(default_factory=list)
    legal: list[LegalMatter] = field(default_factory=list)
    events: list[TimelineEvent] = field(default_factory=list)
    dropped: int = 0  # факты без подтверждённой цитаты

    @property
    def total(self) -> int:
        return (
            len(self.positions)
            + len(self.relations)
            + len(self.companies)
            + len(self.adverse)
            + len(self.legal)
            + len(self.events)
        )


def normalize_text(text: str) -> str:
    return _WS.sub(" ", _DASHES.sub("-", text.translate(_QUOTES))).strip().casefold()


def quote_in_text(quote: str, text: str) -> bool:
    q = normalize_text(quote)
    if len(q) < 8:
        return False
    t = normalize_text(text)
    if q in t:
        return True
    return partial_ratio(q, t) >= _QUOTE_MIN_RATIO


def normalize_date(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if m := _DATE.match(text):
        year, month, day = m.groups()
        if month and not 1 <= int(month) <= 12:
            return year
        if day and not 1 <= int(day) <= 31:
            return f"{year}-{month}"
        return text
    for pattern, order in ((_DMY, "dmy"), (_MDY, "mdy")):
        if m := pattern.search(text):
            day, word = (m[1], m[2]) if order == "dmy" else (m[2], m[1])
            month = _month(word)
            if month and 1 <= int(day) <= 31:
                return f"{m[3]}-{month:02d}-{int(day):02d}"
    if m := _YEAR.search(text):
        return m[1]
    return None


# «Три дочери и три сына», «Turlov family» — описание, а не имя связанного лица
_NOT_A_NAME = re.compile(
    r"(\d|\b(один|одна|два|две|три|четыре|пять|шесть|семь|двое|трое|четверо|пятеро)\b|"
    r"дочер|\bсын(а|ов|овья|ом)?\b|дет[иея]|семь[яи]|супруг|жена\b|муж\b|родител|"
    r"famil|children|daughter|\bsons?\b|wife|husband|parents|relatives)",
    re.IGNORECASE,
)
_SANCTIONS_WORDS = re.compile(r"(санкци|sanction)", re.IGNORECASE)
# Связь должна следовать из цитаты: «№ 17 рейтинга Forbes» — не родство и не партнёрство
_KINSHIP_WORDS = re.compile(
    r"(жен[аы]|супруг|муж\b|мужа|сын|доч|брат|сестр|отец|отца|мать|матер|родител|родств|"
    r"племян|дяд|тёт|тет[яи]|внук|внуч|зят|невестк|тесть|тёщ|свекр|кузен|двоюродн|"
    r"wife|husband|spouse|son\b|sons|daughter|brother|sister|father|mother|parent|relative|"
    r"nephew|niece|uncle|aunt|cousin|grand|in-law|married)",
    re.IGNORECASE,
)
_PARTNER_WORDS = re.compile(
    r"(партн|соратник|совладел|сооснов|соучред|компаньон|друг|близк|доверен|"
    r"partner|associate|co-?owner|co-?founder|ally|confidant|friend|close to)",
    re.IGNORECASE,
)
# Явное указание родства в примечании модели важнее её же поля relation
# («Супруг(а) · father» → parent)
_KIND_HINTS: tuple[tuple[RelationKind, re.Pattern[str]], ...] = (
    (
        RelationKind.SPOUSE,
        re.compile(r"\b(жена|муж|супруг\w*|wife|husband|spouse)\b", re.IGNORECASE),
    ),
    (RelationKind.CHILD, re.compile(r"\b(сын\w*|доч\w*|son|daughter)\b", re.IGNORECASE)),
    (RelationKind.PARENT, re.compile(r"\b(отец|отца|мать|матери|father|mother)\b", re.IGNORECASE)),
    (RelationKind.SIBLING, re.compile(r"\b(брат\w*|сестр\w*|brother|sister)\b", re.IGNORECASE)),
)


def relation_from_note(relation: RelationKind, note: str | None) -> RelationKind:
    if not note:
        return relation
    hinted = {kind for kind, pattern in _KIND_HINTS if pattern.search(note)}
    return hinted.pop() if len(hinted) == 1 else relation


_FAMILY = {
    RelationKind.SPOUSE,
    RelationKind.CHILD,
    RelationKind.PARENT,
    RelationKind.SIBLING,
    RelationKind.OTHER_RELATIVE,
}


def _opt(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _yes_no(value: object) -> bool | None:
    return {"yes": True, "no": False}.get(str(value))


def _share(value: object) -> float | None:
    text = str(value or "").replace(",", ".").replace("%", "").strip()
    try:
        share = float(text)
    except ValueError:
        return None
    return share if 0 <= share <= 100 else None


def _enum_value[E: StrEnum](enum_cls: type[E], value: object, default: E) -> E:
    try:
        return enum_cls(str(value))
    except ValueError:
        return default


# Спорт и благотворительность — не государственный орган, даже если модель решила иначе
# («председатель Национального олимпийского комитета» → non_profit). Узкий список: слово
# «федерация» здесь не годится — «Совет Федерации», «министр … Российской Федерации».
_SPORT_CHARITY = re.compile(
    r"(олимпи|olympic|\bfide\b|фиде|fifa|фифа|uefa|уефа|шахмат|chess|футбол|football|"
    r"хоккe?й|hockey|спортивн|\bsport|благотворит|charit)",
    re.IGNORECASE,
)
_PUBLIC_CATEGORIES = {PositionCategory.STATE_BODY, PositionCategory.PUBLIC_FUNCTION}


def check_category(
    category: PositionCategory, title: str, organization: str | None
) -> PositionCategory:
    """Поправить категорию модели: FIDE, МОК, НОК, FIFA — не органы власти и не межгос. орг."""
    text = f"{title} {organization or ''}"
    if category in _PUBLIC_CATEGORIES:
        return PositionCategory.NON_PROFIT if _SPORT_CHARITY.search(text) else category
    if category is not PositionCategory.INTERNATIONAL_ORG:
        return category
    if _ADVISORY.search(text):
        return PositionCategory.NON_PROFIT
    if _INTERGOVERNMENTAL.search(text):
        return category
    if _NON_GOVERNMENTAL.search(text):
        return PositionCategory.NON_PROFIT
    return category


class FactExtractor:
    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.prompt = load_prompt(PROMPT_NAME)

    async def extract(
        self,
        *,
        source_id: str,
        text: str,
        title: str,
        domain: str,
        name: str,
        latin: str | None,
        extra: str = "",
    ) -> SourceFacts:
        system, user = self.prompt.render(
            name=name,
            latin=latin or "—",
            extra=extra,
            title=title or "без заголовка",
            domain=domain,
            text=text,
        )
        raw = await self.client.complete_json(system=system, user=user, schema=FACTS_SCHEMA)
        facts = parse_facts(raw, source_id=source_id, text=text)
        log.info(
            "llm_facts",
            source=source_id,
            about=facts.about_subject,
            facts=facts.total,
            dropped=facts.dropped,
        )
        return facts


def parse_facts(raw: dict[str, Any], *, source_id: str, text: str) -> SourceFacts:
    """Проверить ответ модели и превратить его в факты с подтверждёнными цитатами."""
    facts = SourceFacts(source_id=source_id, about_subject=str(raw.get("about_subject", "")))
    if facts.about_subject == "no":
        return facts

    def evidence(item: dict[str, Any]) -> list[Evidence] | None:
        quote = str(item.get("quote") or "").strip()
        if quote_in_text(quote, text):
            return [Evidence(source_id=source_id, quote=quote[:300])]
        facts.dropped += 1
        return None

    def items(key: str) -> list[dict[str, Any]]:
        value = raw.get(key)
        return [i for i in value if isinstance(i, dict)] if isinstance(value, list) else []

    for key in ("birth_date", "birth_place"):
        item = raw.get(key)
        if isinstance(item, dict) and _opt(item.get("value")):
            ev = evidence(item)
            value = str(item["value"]).strip()
            if key == "birth_date":
                value = normalize_date(value) or ""
            if ev and value:
                setattr(facts, key, FieldValue(value=value, evidence=ev))

    for item in items("citizenship"):
        code = to_iso2(_opt(item.get("country")))
        if code and (ev := evidence(item)):
            facts.citizenship.append(FieldValue(value=code, evidence=ev))

    for item in items("positions"):
        title = _opt(item.get("title"))
        if title and (ev := evidence(item)):
            facts.positions.append(
                Position(
                    title=title,
                    organization=_opt(item.get("organization")),
                    country=to_iso2(_opt(item.get("country"))),
                    start=normalize_date(str(item.get("start") or "")),
                    end=normalize_date(str(item.get("end") or "")),
                    is_current=_yes_no(item.get("current")),
                    category=check_category(
                        _enum_value(PositionCategory, item.get("category"), PositionCategory.OTHER),
                        title,
                        _opt(item.get("organization")),
                    ),
                    evidence=ev,
                )
            )

    for item in items("relations"):
        name = _opt(item.get("name"))
        if name and _NOT_A_NAME.search(name):
            continue
        relation = relation_from_note(
            _enum_value(RelationKind, item.get("relation"), RelationKind.ASSOCIATE),
            _opt(item.get("note")),
        )
        quote = str(item.get("quote") or "")
        words = _KINSHIP_WORDS if relation in _FAMILY else _PARTNER_WORDS
        if not words.search(f"{quote} {item.get('note') or ''}"):
            continue
        if name and (ev := evidence(item)):
            facts.relations.append(
                Relation(
                    name=name,
                    relation=relation,
                    note=_opt(item.get("note")),
                    is_public_official=_yes_no(item.get("public_official")),
                    evidence=ev,
                )
            )

    for item in items("companies"):
        name = _opt(item.get("name"))
        if name and (ev := evidence(item)):
            facts.companies.append(
                Company(
                    name=name,
                    role=_enum_value(CompanyRole, item.get("role"), CompanyRole.OTHER),
                    share_percent=_share(item.get("share_percent")),
                    country=to_iso2(_opt(item.get("country"))),
                    evidence=ev,
                )
            )

    for item in items("adverse"):
        summary = _opt(item.get("summary"))
        if summary and (ev := evidence(item)):
            facts.adverse.append(
                AdverseItem(
                    category=_enum_value(
                        AdverseCategory, item.get("category"), AdverseCategory.OTHER
                    ),
                    summary=summary,
                    date=normalize_date(str(item.get("date") or "")),
                    severity=_enum_value(Severity, item.get("severity"), Severity.LOW),
                    evidence=ev,
                )
            )

    for item in items("legal"):
        summary = _opt(item.get("summary"))
        # Санкции — не судебное дело: они учитываются в adverse и факторе «Санкции»
        if summary and _SANCTIONS_WORDS.search(summary):
            continue
        if summary and (ev := evidence(item)):
            facts.legal.append(
                LegalMatter(
                    kind=_enum_value(LegalKind, item.get("kind"), LegalKind.INVESTIGATION),
                    summary=summary,
                    jurisdiction=to_iso2(_opt(item.get("jurisdiction")))
                    or _opt(item.get("jurisdiction")),
                    status=_opt(item.get("status")),
                    date=normalize_date(str(item.get("date") or "")),
                    evidence=ev,
                )
            )

    for item in items("events"):
        summary = _opt(item.get("summary"))
        date = normalize_date(str(item.get("date") or ""))
        if summary and date and (ev := evidence(item)):
            facts.events.append(
                TimelineEvent(date=date, summary=summary, kind="event", source_id=ev[0].source_id)
            )
    return facts
