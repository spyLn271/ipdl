"""Разбор официальных санкционных списков в единый формат :class:`SanctionsEntry`.

Поддерживаемые форматы (``format`` в ``methodology/sanctions-sources.yaml``):

* ``un`` — сводный список Совета Безопасности ООН (consolidated.xml);
* ``ofac_sdn`` — OFAC Specially Designated Nationals (SDN.XML, Минфин США);
* ``eu_fsf`` — сводный список финансовых санкций ЕС (Financial Sanctions Files, XML 1.1);
* ``uk_fcdo`` — UK Sanctions List (FCDO, XML).

XML читается потоково (``iterparse``) без DTD, внешних сущностей и сети — файлы большие
(до 30 МБ) и приходят из интернета.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from lxml import etree

type EntityType = Literal["person", "entity", "vessel", "aircraft", "other"]

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}
_SPACES = re.compile(r"\s+")


class SanctionsParseError(ValueError):
    pass


@dataclass(slots=True)
class SanctionsEntry:
    ref: str
    entity_type: EntityType
    primary_name: str
    names: list[str] = field(default_factory=list)
    birth_dates: list[str] = field(default_factory=list)
    nationalities: list[str] = field(default_factory=list)
    programs: list[str] = field(default_factory=list)
    listed_on: str | None = None
    remarks: str | None = None

    def add_name(self, name: str | None) -> None:
        clean = _clean(name)
        if clean and clean not in self.names:
            self.names.append(clean)


def _clean(value: str | None) -> str:
    return _SPACES.sub(" ", value or "").strip()


def _local(el: etree._Element) -> str:
    return etree.QName(el).localname


def _children(el: etree._Element, name: str) -> list[etree._Element]:
    return [c for c in el if isinstance(c.tag, str) and _local(c) == name]


def _child(el: etree._Element, name: str) -> etree._Element | None:
    found = _children(el, name)
    return found[0] if found else None


def _text(el: etree._Element | None, name: str | None = None) -> str:
    if el is None:
        return ""
    target = _child(el, name) if name else el
    return _clean(target.text) if target is not None and target.text else ""


def _descendants(el: etree._Element, name: str) -> Iterator[etree._Element]:
    for d in el.iter():
        if isinstance(d.tag, str) and _local(d) == name:
            yield d


def _iter_records(path: Path, record: str) -> Iterator[etree._Element]:
    try:
        for _, el in etree.iterparse(
            str(path),
            events=("end",),
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=True,
            remove_comments=True,
        ):
            if isinstance(el.tag, str) and _local(el) == record:
                yield el
                el.clear(keep_tail=False)
                parent = el.getparent()
                while parent is not None and el.getprevious() is not None:
                    del parent[0]
    except etree.XMLSyntaxError as exc:
        raise SanctionsParseError(f"{path.name}: некорректный XML: {exc}") from exc


# ---------------------------------------------------------------- даты


def normalize_date(raw: str) -> str | None:
    """Привести дату из списка к ISO-префиксу: ``1987-11-13``, ``1987-11`` или ``1987``.

    >>> normalize_date("10 Dec 1948"), normalize_date("dd/mm/1945"), normalize_date("13/11/1987")
    ('1948-12-10', '1945', '1987-11-13')
    """
    text = _clean(raw).lower().replace("circa", "").replace("approximately", "").strip()
    if not text:
        return None
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:t.*)?", text):
        return f"{m[1]}-{m[2]}-{m[3]}"
    if m := re.fullmatch(r"(\d{1,2}|dd)/(\d{1,2}|mm)/(\d{4})", text):
        day, month, year = m[1], m[2], m[3]
        if month == "mm":
            return year
        if day == "dd":
            return f"{year}-{int(month):02d}"
        return f"{year}-{int(month):02d}-{int(day):02d}"
    if m := re.fullmatch(r"(\d{1,2}) ([a-z]{3})[a-z]* (\d{4})", text):
        month_no = _MONTHS.get(m[2])
        return f"{m[3]}-{month_no:02d}-{int(m[1]):02d}" if month_no else m[3]
    if m := re.fullmatch(r"([a-z]{3})[a-z]* (\d{4})", text):
        month_no = _MONTHS.get(m[1])
        return f"{m[2]}-{month_no:02d}" if month_no else m[2]
    if m := re.search(r"\b(1[89]\d{2}|20\d{2})\b", text):
        return m[1]
    return None


def _year_range(start: str, end: str) -> list[str]:
    if not (start.isdigit() and end.isdigit()):
        return [y for y in (start, end) if y.isdigit()]
    first, last = int(start), int(end)
    if last < first or last - first > 15:
        return [start, end]
    return [str(y) for y in range(first, last + 1)]


def _add_date(entry: SanctionsEntry, raw: str) -> None:
    value = normalize_date(raw)
    if value and value not in entry.birth_dates:
        entry.birth_dates.append(value)


def _add_unique(items: list[str], value: str) -> None:
    clean = _clean(value)
    if clean and clean not in items:
        items.append(clean)


# ---------------------------------------------------------------- ООН


def parse_un(path: Path) -> Iterator[SanctionsEntry]:
    for record in ("INDIVIDUAL", "ENTITY"):
        for el in _iter_records(path, record):
            yield _un_entry(el, "person" if record == "INDIVIDUAL" else "entity")


def _un_entry(el: etree._Element, entity_type: EntityType) -> SanctionsEntry:
    parts = [_text(el, n) for n in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
    primary = " ".join(p for p in parts if p)
    entry = SanctionsEntry(
        ref=_text(el, "REFERENCE_NUMBER") or _text(el, "DATAID"),
        entity_type=entity_type,
        primary_name=primary,
        listed_on=normalize_date(_text(el, "LISTED_ON")),
        remarks=_text(el, "COMMENTS1") or None,
    )
    entry.add_name(primary)
    entry.add_name(_text(el, "NAME_ORIGINAL_SCRIPT"))
    for alias in [*_children(el, "INDIVIDUAL_ALIAS"), *_children(el, "ENTITY_ALIAS")]:
        entry.add_name(_text(alias, "ALIAS_NAME"))
    for dob in _children(el, "INDIVIDUAL_DATE_OF_BIRTH"):
        if date := _text(dob, "DATE"):
            _add_date(entry, date)
        elif year := _text(dob, "YEAR"):
            _add_date(entry, year)
        elif (start := _text(dob, "FROM_YEAR")) or _text(dob, "TO_YEAR"):
            for year in _year_range(start, _text(dob, "TO_YEAR")):
                _add_date(entry, year)
    for nat in _children(el, "NATIONALITY"):
        for value in _children(nat, "VALUE"):
            _add_unique(entry.nationalities, _text(value))
    _add_unique(entry.programs, _text(el, "UN_LIST_TYPE"))
    return entry


# ---------------------------------------------------------------- OFAC SDN

_OFAC_TYPES: dict[str, EntityType] = {
    "individual": "person",
    "entity": "entity",
    "vessel": "vessel",
    "aircraft": "aircraft",
}


def _ofac_name(el: etree._Element) -> str:
    return " ".join(p for p in (_text(el, "firstName"), _text(el, "lastName")) if p)


def parse_ofac_sdn(path: Path) -> Iterator[SanctionsEntry]:
    for el in _iter_records(path, "sdnEntry"):
        primary = _ofac_name(el)
        entry = SanctionsEntry(
            ref=_text(el, "uid"),
            entity_type=_OFAC_TYPES.get(_text(el, "sdnType").lower(), "other"),
            primary_name=primary,
            remarks=_text(el, "remarks") or _text(el, "title") or None,
        )
        entry.add_name(primary)
        for aka in _descendants(el, "aka"):
            entry.add_name(_ofac_name(aka))
        for dob in _descendants(el, "dateOfBirth"):
            _add_date(entry, _text(dob))
        for tag in ("nationality", "citizenship"):
            for item in _descendants(el, tag):
                _add_unique(entry.nationalities, _text(item, "country"))
        for program in _descendants(el, "program"):
            _add_unique(entry.programs, _text(program))
        yield entry


# ---------------------------------------------------------------- ЕС: Financial Sanctions Files

_EU_TYPES: dict[str, EntityType] = {"person": "person", "enterprise": "entity"}


def parse_eu_fsf(path: Path) -> Iterator[SanctionsEntry]:
    for el in _iter_records(path, "sanctionEntity"):
        subject = _child(el, "subjectType")
        code = subject.get("code", "") if subject is not None else ""
        aliases = _children(el, "nameAlias")
        names = [_clean(a.get("wholeName")) for a in aliases]
        primary = next((n for n in names if n), "")
        entry = SanctionsEntry(
            ref=el.get("euReferenceNumber") or el.get("logicalId") or "",
            entity_type=_EU_TYPES.get(code, "other"),
            primary_name=primary,
            remarks=_text(el, "remark") or None,
        )
        for name in names:
            entry.add_name(name)
        for birth in _children(el, "birthdate"):
            raw = birth.get("birthdate") or birth.get("year") or ""
            if raw:
                _add_date(entry, raw)
        for cit in _children(el, "citizenship"):
            _add_unique(entry.nationalities, cit.get("countryIso2Code", "").replace("00", ""))
        regulations = _children(el, "regulation")
        for regulation in regulations:
            _add_unique(entry.programs, regulation.get("programme", ""))
        dates = sorted(d for r in regulations if (d := r.get("publicationDate")))
        entry.listed_on = normalize_date(dates[0]) if dates else None
        yield entry


# ---------------------------------------------------------------- Великобритания: список FCDO

_UK_TYPES: dict[str, EntityType] = {"individual": "person", "entity": "entity", "ship": "vessel"}


def parse_uk_fcdo(path: Path) -> Iterator[SanctionsEntry]:
    for el in _iter_records(path, "Designation"):
        names: list[tuple[str, str]] = []
        for name_el in _descendants(el, "Name"):
            parts = [_text(name_el, f"Name{i}") for i in range(1, 7)]
            full = " ".join(p for p in parts if p)
            names.append((full, _text(name_el, "NameType")))
        primary = next((n for n, kind in names if kind == "Primary Name"), "") or (
            names[0][0] if names else ""
        )
        entry = SanctionsEntry(
            ref=_text(el, "UniqueID"),
            entity_type=_UK_TYPES.get(_text(el, "IndividualEntityShip").lower(), "other"),
            primary_name=primary,
            listed_on=normalize_date(_text(el, "DateDesignated")),
            remarks=_text(el, "OtherInformation") or None,
        )
        for name, _kind in names:
            entry.add_name(name)
        for non_latin in _descendants(el, "NameNonLatinScript"):
            entry.add_name(_text(non_latin))
        for dob in _descendants(el, "DOB"):
            _add_date(entry, _text(dob))
        for nat in _descendants(el, "Nationality"):
            _add_unique(entry.nationalities, _text(nat))
        _add_unique(entry.programs, _text(el, "RegimeName"))
        yield entry


PARSERS: dict[str, Callable[[Path], Iterator[SanctionsEntry]]] = {
    "un": parse_un,
    "ofac_sdn": parse_ofac_sdn,
    "eu_fsf": parse_eu_fsf,
    "uk_fcdo": parse_uk_fcdo,
}


def parse(fmt: str, path: Path) -> Iterator[SanctionsEntry]:
    try:
        parser = PARSERS[fmt]
    except KeyError:
        raise SanctionsParseError(f"Неизвестный формат списка: {fmt}") from None
    return parser(path)


def published_at(fmt: str, path: Path) -> str | None:
    """Дата формирования списка из заголовка файла (читается только начало файла)."""
    with path.open("rb") as stream:
        head = stream.read(4096).decode("utf-8", errors="replace")
    patterns = {
        "un": r'dateGenerated="([^"]+)"',
        "ofac_sdn": r"<Publish_Date>([^<]+)</Publish_Date>",
        "eu_fsf": r'generationDate="([^"]+)"',
        "uk_fcdo": r"<DateGenerated>([^<]+)</DateGenerated>",
    }
    pattern = patterns.get(fmt)
    m = re.search(pattern, head) if pattern else None
    if not m:
        return None
    raw = m[1]
    if fmt == "ofac_sdn" and (us := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)):
        return f"{us[3]}-{int(us[1]):02d}-{int(us[2]):02d}"
    return normalize_date(raw[:10]) if fmt != "uk_fcdo" else normalize_date(raw)
