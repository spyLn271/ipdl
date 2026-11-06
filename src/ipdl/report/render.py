"""Экспорт портрета: DOCX («Аналитический портрет» для комплаенс-досье) и PDF (как на экране).

Структура DOCX повторяет образец аналитического портрета (предварительная AML/KYC-оценка):
идентификация, профиль, статус ИПДЛ, риск-матрица, заключение, источники для верификации —
и дополнена санкционным скринингом, негативными сведениями и связанными лицами.
"""

from __future__ import annotations

import asyncio
import io
from datetime import UTC, datetime
from functools import cache
from importlib import resources

import docx
import jinja2
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from ipdl.analysis.conclusion import LEVEL_TITLES, PEP_TITLES
from ipdl.analysis.model import Portrait, Position, Review, RiskLevel
from ipdl.config.settings import OrgSettings
from ipdl.geo import country_name
from ipdl.report import labels
from ipdl.report.labels import DOB_MATCH

_LEVEL_COLORS = {
    RiskLevel.LOW: RGBColor(0x16, 0x65, 0x34),
    RiskLevel.MEDIUM: RGBColor(0x9A, 0x34, 0x12),
    RiskLevel.HIGH: RGBColor(0xB9, 0x1C, 0x1C),
    RiskLevel.NO_DATA: RGBColor(0x52, 0x52, 0x52),
}


def _countries(codes: list[str]) -> str:
    return ", ".join(country_name(c) or c for c in codes) or "не установлено"


def _period(position: Position) -> str:
    if position.start and position.end:
        return f"{position.start} — {position.end}"
    if position.start:
        return f"с {position.start}" + (" по н. в." if position.is_current else "")
    if position.end:
        return f"по {position.end}"
    return "по н. в." if position.is_current else "период не указан"


def _sources_ref(ids: list[str]) -> str:
    return f" [{', '.join(ids)}]" if ids else ""


# ---------------------------------------------------------------- DOCX


class _Writer:
    """Тонкая обёртка над python-docx: заголовки, абзацы, списки."""

    def __init__(self) -> None:
        self.document = docx.Document()
        normal = self.document.styles["Normal"]
        normal.font.name = "Arial"
        normal.font.size = Pt(10.5)

    def heading(self, text: str) -> None:
        self.document.add_heading(text, level=1)

    def bullet(self, text: str) -> None:
        self.document.add_paragraph(text, style="List Bullet")

    def para(self, text: str, *, bold: bool = False, italic: bool = False) -> None:
        run = self.document.add_paragraph().add_run(text)
        run.bold, run.italic = bold, italic

    def centered(
        self, text: str, *, bold: bool = False, italic: bool = False, size: int = 0
    ) -> None:
        paragraph = self.document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        run.bold, run.italic = bold, italic
        if size:
            run.font.size = Pt(size)

    def save(self) -> bytes:
        buffer = io.BytesIO()
        self.document.save(buffer)
        return buffer.getvalue()


def _identity_section(w: _Writer, portrait: Portrait) -> None:
    identity = portrait.identity
    w.heading("1. Идентификация и публичная деятельность")
    latin = f" ({identity.latin_name})" if identity.latin_name else ""
    w.bullet(f"ФИО: {identity.full_name}{latin}.")
    if identity.birth_date:
        refs = _sources_ref([e.source_id for e in identity.birth_date.evidence])
        w.bullet(f"Дата рождения: {identity.birth_date.value}{refs}.")
    if identity.birth_place:
        w.bullet(f"Место рождения: {identity.birth_place.value}.")
    w.bullet(f"Гражданство: {_countries(identity.citizenship)}.")
    for field, values in identity.conflicts.items():
        name = {"birth_date": "дате рождения", "birth_place": "месту рождения"}.get(field, field)
        w.bullet(f"Источники расходятся по {name}: {', '.join(values)} — требуется проверка.")
    if portrait.positions:
        top = portrait.positions[0]
        where = f", {top.organization}" if top.organization else ""
        w.bullet(f"Основная деятельность: {top.title}{where}.")
    w.bullet(f"Публичный статус (предварительно): {PEP_TITLES[portrait.pep.category]}.")


def _profile_section(w: _Writer, portrait: Portrait) -> None:
    w.heading("2. Профессиональный и корпоративный профиль")
    if not portrait.positions and not portrait.companies:
        w.para("Сведения о должностях и компаниях в найденных источниках отсутствуют.")
    for position in portrait.positions[:12]:
        where = f", {position.organization}" if position.organization else ""
        country = f", {country_name(position.country)}" if position.country else ""
        refs = _sources_ref([e.source_id for e in position.evidence])
        w.bullet(
            f"{position.title}{where}{country} ({_period(position)}; "
            f"{labels.POSITION_CATEGORY[position.category]}){refs}."
        )
    for company in portrait.companies[:12]:
        share = f", доля {company.share_percent:g} %" if company.share_percent is not None else ""
        country = f", {country_name(company.country)}" if company.country else ""
        refs = _sources_ref([e.source_id for e in company.evidence])
        w.bullet(f"{company.name}: {labels.COMPANY_ROLE[company.role]}{share}{country}{refs}.")


_TO_VERIFY = (
    "статус ПДЛ/ИПДЛ по применимому законодательству и внутренним правилам организации;",
    "родственные и близкие деловые связи с публичными должностными лицами;",
    "актуальные санкционные перечни и применимые ограничения;",
    "негативные публикации, судебные и регуляторные сведения;",
    "актуальную структуру владения, корпоративные связи и источники состояния.",
)


def _pep_section(w: _Writer, portrait: Portrait) -> None:
    pep = portrait.pep
    w.heading("3. Предварительная оценка статуса ИПДЛ")
    w.para(f"Предварительный вывод: {pep.rationale}")
    if pep.clause:
        w.para(f"Правовое основание: {pep.clause}.", italic=True)
    if pep.measures:
        w.para("Меры надлежащей проверки (п. 1 ст. 8 Закона РК № 191-IV):")
        for measure in pep.measures:
            w.bullet(measure)
    w.para("Для окончательной классификации необходимо проверить:")
    for item in _TO_VERIFY:
        w.bullet(item)


def _risk_section(w: _Writer, portrait: Portrait) -> None:
    risk = portrait.risk
    w.heading("4. Предварительная риск-матрица")
    table = w.document.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    for cell, text in zip(
        table.rows[0].cells, ("Параметр", "Результат", "Комментарий"), strict=True
    ):
        cell.text = ""
        cell.paragraphs[0].add_run(text).bold = True
    for factor in risk.factors:
        cells = table.add_row().cells
        cells[0].text = labels.FACTOR[factor.key]
        level = cells[1].paragraphs[0].add_run(labels.LEVEL[factor.level])
        level.bold = True
        level.font.color.rgb = _LEVEL_COLORS[factor.level]
        cells[2].text = factor.comment + (" (решение аналитика)" if factor.overridden else "")
    cells = table.add_row().cells
    cells[0].paragraphs[0].add_run("Итоговый AML-риск").bold = True
    total = (
        cells[1]
        .paragraphs[0]
        .add_run(f"{LEVEL_TITLES[risk.level].capitalize()} — {risk.score}/100")
    )
    total.bold = True
    total.font.color.rgb = _LEVEL_COLORS[risk.level]
    floors = " " + " ".join(risk.floors) if risk.floors else ""
    cells[2].text = (
        f"{risk.method_title}. Дата оценки: {risk.assessed_at:%d.%m.%Y}. "
        f"Следующий пересмотр: {risk.next_review:%d.%m.%Y}.{floors}"
    )


def _sanctions_section(w: _Writer, portrait: Portrait) -> None:
    checked = portrait.sanctions
    w.heading("5. Санкционный скрининг")
    if checked.lists:
        w.para("Проверены официальные перечни:")
        for status in checked.lists:
            on = f" (на {status.published_at:%d.%m.%Y})" if status.published_at else ""
            w.bullet(f"{status.name}{on}, записей: {status.entries}.")
    else:
        w.para("Санкционные списки не были загружены — скрининг не выполнен.")
    if checked.matches:
        w.para("Возможные совпадения (требуют ручной проверки):", bold=True)
        for match in checked.matches:
            dob = DOB_MATCH[match.dob_match]
            w.bullet(
                f"{match.list_name}: {match.primary_name} ({match.entry_ref}), сходство "
                f"{match.score:.0f}%, {dob}; программы: {', '.join(match.programs) or '—'}."
            )
    elif checked.lists:
        w.para("Совпадений с проверяемым лицом не найдено.")
    for match in checked.related:
        w.bullet(
            f"Связанное лицо/компания «{match.query}» — {match.list_name}: {match.primary_name}."
        )


def _adverse_section(w: _Writer, portrait: Portrait) -> None:
    w.heading("6. Негативные публикации и правовые сведения")
    if not portrait.adverse and not portrait.legal:
        w.para("В проанализированных источниках негативных сведений не найдено.")
    for item in portrait.adverse:
        refs = _sources_ref([e.source_id for e in item.evidence])
        when = f"{item.date}: " if item.date else ""
        w.bullet(
            f"{when}{item.summary} ({labels.ADVERSE[item.category]}, значимость — "
            f"{labels.SEVERITY[item.severity]}){refs}."
        )
    for matter in portrait.legal:
        refs = _sources_ref([e.source_id for e in matter.evidence])
        when = f"{matter.date}: " if matter.date else ""
        status = f", статус: {matter.status}" if matter.status else ""
        w.bullet(f"{when}{matter.summary} ({labels.LEGAL[matter.kind]}{status}){refs}.")


def _relations_section(w: _Writer, portrait: Portrait) -> None:
    w.heading("7. Связанные лица")
    if not portrait.relations:
        w.para("Связанные лица в источниках не установлены.")
    for relation in portrait.relations:
        refs = _sources_ref([e.source_id for e in relation.evidence])
        note = f" — {relation.note}" if relation.note else ""
        official = " (публичное должностное лицо)" if relation.is_public_official else ""
        w.bullet(f"{relation.name}: {labels.RELATION[relation.relation]}{official}{note}{refs}.")
    if portrait.timeline:
        w.heading("8. Хронология")
        for event in portrait.timeline[-25:]:
            ref = f" [{event.source_id}]" if event.source_id else ""
            w.bullet(f"{event.date} — {event.summary}{ref}")


def _closing_section(
    w: _Writer, portrait: Portrait, review: Review | None, org: OrgSettings
) -> None:
    w.heading("9. Заключение для комплаенс-досье")
    w.para(portrait.conclusion)
    if review and review.reviewer and review.reviewed_at:
        w.para(
            f"Решение аналитика: {review.reviewer}, {review.reviewed_at:%d.%m.%Y %H:%M} UTC.",
            italic=True,
        )
    w.heading("10. Источники для верификации")
    used = [s for s in portrait.sources if s.analyzed or s.fetched][:40] or portrait.sources[:20]
    for source in used:
        w.bullet(
            f"[{source.id}] {source.title} — {source.url} ({labels.SOURCE_KIND[source.kind]}, "
            f"обращение {source.retrieved_at:%d.%m.%Y}, {labels.VERIFICATION[source.verification]})"
        )
    for limitation in portrait.limitations:
        w.para(f"Ограничение: {limitation}", italic=True)
    w.para(org.legal_notice, italic=True)


def render_docx(
    portrait: Portrait, *, review: Review | None, org: OrgSettings, version: int
) -> bytes:
    w = _Writer()
    w.centered("АНАЛИТИЧЕСКИЙ ПОРТРЕТ", bold=True, size=16)
    w.centered(f"{portrait.identity.full_name} — предварительная AML/KYC-оценка", bold=True)
    w.centered(
        f"{org.system_name} · {org.authority} · версия {version} · сформирован "
        f"{portrait.generated_at:%d.%m.%Y}, выгружен {datetime.now(UTC):%d.%m.%Y}",
        italic=True,
    )
    w.para(
        "Назначение документа: предварительный аналитический профиль для комплаенс-проверки. "
        "Документ не является официальным заключением и требует верификации по актуальным "
        "источникам."
    )
    _identity_section(w, portrait)
    _profile_section(w, portrait)
    _pep_section(w, portrait)
    _risk_section(w, portrait)
    _sanctions_section(w, portrait)
    _adverse_section(w, portrait)
    _relations_section(w, portrait)
    _closing_section(w, portrait, review, org)
    return w.save()


# ---------------------------------------------------------------- PDF


@cache
def _environment() -> jinja2.Environment:
    loader = jinja2.FunctionLoader(
        lambda name: (
            resources.files("ipdl.report").joinpath("templates", name).read_text(encoding="utf-8")
        )
    )
    env = jinja2.Environment(loader=loader, autoescape=True, undefined=jinja2.StrictUndefined)
    env.filters["country"] = lambda code: country_name(code) or code or ""
    env.filters["countries"] = _countries
    env.filters["period"] = _period
    return env


def render_html(
    portrait: Portrait, *, review: Review | None, org: OrgSettings, version: int
) -> str:
    template = _environment().get_template("portrait.html")
    return template.render(
        p=portrait,
        review=review,
        org=org,
        version=version,
        labels=labels,
        level_titles=LEVEL_TITLES,
        pep_titles=PEP_TITLES,
        exported_at=datetime.now(UTC),
    )


def _html_to_pdf(html: str) -> bytes:
    from weasyprint import HTML  # noqa: PLC0415 — тяжёлый импорт (pango) только для PDF

    # base_url=None и url_fetcher без сети: шаблон не ссылается на внешние ресурсы
    def no_fetch(url: str) -> dict[str, object]:
        raise ValueError(f"внешние ресурсы в PDF запрещены: {url}")

    return bytes(HTML(string=html, url_fetcher=no_fetch).write_pdf())


async def render_pdf(
    portrait: Portrait, *, review: Review | None, org: OrgSettings, version: int
) -> bytes:
    html = render_html(portrait, review=review, org=org, version=version)
    return await asyncio.to_thread(_html_to_pdf, html)
