"""Извлечение основного текста страницы и фрагментов, где упоминается лицо.

HTML — trafilatura (убирает меню, рекламу, комментарии), PDF — pypdfium2.
Модели передаются не страницы целиком, а абзацы с упоминанием лица и ближайшие к ним:
так в контекст помещается больше источников, а цитаты легче проверить.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

import trafilatura

from ipdl.fetch.fetcher import FetchedDocument
from ipdl.logs import get_logger
from ipdl.search.collect import NameForms, mentions

log = get_logger(__name__)

_MAX_PDF_PAGES = 40
_SPLIT = re.compile(r"\n\s*\n|\n")
_SPACES = re.compile(r"[ \t ]+")
# Абзац с одним токеном имени («Турлов также…») берём, если он недалеко после полного упоминания
_FOLLOW_WINDOW = 3
# Ударения («Турло́в»), сноски («[1]», «[2][5]») и служебные ссылки вики
_STRESS = re.compile("[̀́]")
_FOOTNOTES = re.compile(r"\[(?:\d{1,3}|[a-z]|прим\. \d+|nb \d+)\]")
_WIKI_EDIT = re.compile(r"\[\s*править(?: \| править код)?\s*\]|\[\s*edit\s*\]", re.IGNORECASE)
_MIN_PARAGRAPH = 25


@dataclass(slots=True)
class ExtractedText:
    title: str | None
    text: str
    published: date | None


def extract_text(doc: FetchedDocument) -> ExtractedText | None:
    if doc.content_type == "application/pdf":
        return _extract_pdf(doc.body)
    if doc.content_type == "text/plain":
        return ExtractedText(None, doc.body.decode("utf-8", errors="replace"), None)
    result = trafilatura.bare_extraction(
        doc.body,
        url=doc.final_url,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
        with_metadata=True,
    )
    if result is None:
        return None
    text = getattr(result, "text", None) or ""
    if not text.strip():
        return None
    return ExtractedText(
        title=getattr(result, "title", None),
        text=text,
        published=_parse_date(getattr(result, "date", None)),
    )


def _extract_pdf(body: bytes) -> ExtractedText | None:
    import pypdfium2  # noqa: PLC0415 — тяжёлый импорт, нужен только для PDF

    try:
        pdf = pypdfium2.PdfDocument(body)
    except pypdfium2.PdfiumError:
        return None
    try:
        pages = [
            pdf[i].get_textpage().get_text_range() for i in range(min(len(pdf), _MAX_PDF_PAGES))
        ]
    finally:
        pdf.close()
    text = "\n".join(p.replace("\r", "") for p in pages)
    return ExtractedText(None, text, None) if text.strip() else None


def clean_paragraph(text: str) -> str:
    text = unicodedata.normalize("NFC", _STRESS.sub("", unicodedata.normalize("NFD", text)))
    text = _WIKI_EDIT.sub("", _FOOTNOTES.sub("", text))
    return _SPACES.sub(" ", text).strip()


def _parse_date(raw: object) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def relevant_passages(text: str, forms: NameForms, max_chars: int) -> str:
    """Абзацы с упоминанием лица (и продолжения рядом с ними), не длиннее ``max_chars``."""
    paragraphs = [clean_paragraph(p) for p in _SPLIT.split(text)]
    # Таблицы (инфобоксы) и обрывки меню — шум для модели
    paragraphs = [p for p in paragraphs if len(p) >= _MIN_PARAGRAPH and not p.startswith("|")]
    full = min(2, len(forms.stems))
    keep: list[int] = []
    last_anchor = -100
    for index, paragraph in enumerate(paragraphs):
        hits = mentions(paragraph, forms)
        if hits >= full:
            last_anchor = index
            keep.append(index)
        elif (hits >= 1 and index - last_anchor <= _FOLLOW_WINDOW) or index - last_anchor == 1:
            # продолжение рассказа о лице: «Окончил школу в 2003 году…»
            keep.append(index)
    out: list[str] = []
    size = 0
    for index in keep:
        paragraph = paragraphs[index]
        if size + len(paragraph) > max_chars:
            remaining = max_chars - size
            if remaining > 200:
                out.append(paragraph[:remaining].rsplit(" ", 1)[0] + " …")
            break
        out.append(paragraph)
        size += len(paragraph) + 1
    return "\n".join(out)
