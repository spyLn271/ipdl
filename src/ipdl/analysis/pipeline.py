"""Построение аналитического портрета: поиск → загрузка → санкции → факты → оценка.

Каждый этап сообщает прогресс (для интерфейса) и деградирует мягко: недоступен SearXNG —
портрет строится по санкционным спискам и данным аналитика; недоступна LLM — источники
и скрининг есть, факты не извлечены; всё это попадает в ``warnings`` портрета.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Protocol

from ipdl.analysis.aggregate import build_identity, build_timeline, merge_facts
from ipdl.analysis.conclusion import LIMITATIONS, headline_of, write_conclusion
from ipdl.analysis.methodology import Jurisdictions, RiskModel
from ipdl.analysis.model import (
    Company,
    Portrait,
    Relation,
    RunStats,
    SanctionsCheck,
    SanctionsListStatus,
    SanctionsMatch,
    Source,
    Subject,
)
from ipdl.analysis.pep import assess_pep
from ipdl.analysis.risk import RiskInputs, assess_risk
from ipdl.config.settings import Settings
from ipdl.fetch.extract import extract_text, relevant_passages
from ipdl.fetch.fetcher import Fetcher, FetchError
from ipdl.llm.client import LLMError
from ipdl.llm.extract import FactExtractor, SourceFacts
from ipdl.logs import get_logger
from ipdl.search.collect import Candidate, Collection, NameForms, QueryPlan, collect, name_forms
from ipdl.search.searxng import SearxngClient

log = get_logger(__name__)


class Stage(StrEnum):
    SEARCH = "search"
    FETCH = "fetch"
    SANCTIONS = "sanctions"
    EXTRACT = "extract"
    ASSESS = "assess"


# Доля шкалы прогресса (0–100) на этап: дольше всего работает языковая модель
_SPAN: dict[Stage, tuple[int, int]] = {
    Stage.SEARCH: (0, 20),
    Stage.FETCH: (20, 35),
    Stage.SANCTIONS: (35, 40),
    Stage.EXTRACT: (40, 95),
    Stage.ASSESS: (95, 100),
}
_RELATED_SCREEN_LIMIT = 15

type Progress = Callable[[Stage, int], Awaitable[None]]


class SanctionsScreener(Protocol):
    async def screen(
        self, names: Sequence[str], *, birth_date: date | None, entity_types: Sequence[str]
    ) -> list[SanctionsMatch]: ...

    async def lists(self) -> list[SanctionsListStatus]: ...


@dataclass(slots=True)
class Deps:
    settings: Settings
    plan: QueryPlan
    model: RiskModel
    jurisdictions: Jurisdictions
    searxng: SearxngClient | None
    fetcher: Fetcher | None
    extractor: FactExtractor | None
    sanctions: SanctionsScreener


@dataclass(slots=True)
class _Text:
    title: str
    text: str


@dataclass(slots=True)
class _Run:
    subject: Subject
    deps: Deps
    report: Progress
    forms: NameForms
    now: datetime
    warnings: list[str] = field(default_factory=list)

    async def step(self, stage: Stage, done: int, total: int) -> None:
        low, high = _SPAN[stage]
        await self.report(stage, low + (high - low) * min(done, total) // max(total, 1))


async def _no_progress(_stage: Stage, _percent: int) -> None:
    return None


async def build_portrait(
    subject: Subject, deps: Deps, progress: Progress | None = None
) -> Portrait:
    started = time.perf_counter()
    run = _Run(
        subject=subject,
        deps=deps,
        report=progress or _no_progress,
        forms=name_forms(subject),
        now=datetime.now(UTC),
    )
    settings = deps.settings

    collection, search_ok = await _search(run)
    sources = [_source(i, c, run.now) for i, c in enumerate(collection.candidates)]
    texts = await _fetch(run, sources)
    lists, matches = await _screen_subject(run)
    facts, llm_used = await _extract(run, sources, texts)

    await run.step(Stage.ASSESS, 0, 1)
    positions, relations, companies, adverse, legal, events = merge_facts(facts)
    identity = build_identity(subject, run.forms.latin, facts)
    home = settings.org.home_country
    pep = assess_pep(positions, relations, home_country=home, model=deps.model)
    related = await _screen_related(deps.sanctions, relations, companies)
    sanctions = SanctionsCheck(checked_at=run.now, lists=lists, matches=matches, related=related)
    risk = assess_risk(
        RiskInputs(
            pep=pep,
            identity=identity,
            positions=positions,
            relations=relations,
            companies=companies,
            adverse=adverse,
            legal=legal,
            sanctions=sanctions,
            home_country=home,
            search_ok=search_ok,
            lists_loaded=bool(lists),
        ),
        model=deps.model,
        jurisdictions=deps.jurisdictions,
        now=run.now,
    )
    portrait = Portrait(
        subject=subject,
        identity=identity,
        pep=pep,
        risk=risk,
        positions=positions,
        relations=relations,
        companies=companies,
        adverse=adverse,
        legal=legal,
        timeline=build_timeline(positions, events, adverse, legal),
        sanctions=sanctions,
        sources=sources,
        conclusion="",
        limitations=LIMITATIONS,
        warnings=run.warnings,
        stats=RunStats(
            search_ok=search_ok,
            llm_used=llm_used,
            queries=collection.queries,
            results=collection.results,
            sources=len(sources),
            fetched=sum(1 for s in sources if s.fetched),
            analyzed=sum(1 for s in sources if s.analyzed),
            duration_s=round(time.perf_counter() - started, 1),
            model=settings.llm.model if llm_used else None,
        ),
        generated_at=run.now,
    )
    portrait.conclusion = write_conclusion(
        full_name=identity.full_name, headline=headline_of(portrait), pep=pep, risk=risk
    )
    await run.step(Stage.ASSESS, 1, 1)
    log.info(
        "portrait_built",
        sources=len(sources),
        facts=sum(f.total for f in facts),
        pep=pep.category.value,
        score=risk.score,
        seconds=portrait.stats.duration_s,
    )
    return portrait


# ---------------------------------------------------------------- этапы


async def _search(run: _Run) -> tuple[Collection, bool]:
    await run.step(Stage.SEARCH, 0, 1)
    empty = Collection(candidates=[], queries=0, results=0, unresponsive={}, failed_queries=0)
    client = run.deps.searxng
    if client is None:
        run.warnings.append("Поиск по открытым источникам отключён.")
        return empty, False
    settings = run.deps.settings.search
    collection = await collect(
        client,
        run.deps.plan,
        run.subject,
        max_concurrency=settings.max_concurrency,
        max_sources=settings.max_sources,
        stagger_s=settings.stagger_s,
        on_progress=lambda done, total: run.step(Stage.SEARCH, done, total),
    )
    search_ok = collection.failed_queries < collection.queries
    if not search_ok:
        run.warnings.append("Поиск по открытым источникам не выполнен: SearXNG недоступен.")
    elif collection.failed_queries:
        run.warnings.append(
            f"Часть поисковых запросов не выполнена ({collection.failed_queries} из "
            f"{collection.queries})."
        )
    flaky = sorted(e for e, n in collection.unresponsive.items() if n * 2 >= collection.queries)
    if flaky:
        run.warnings.append(f"Поисковики отвечали с ошибками: {', '.join(flaky)}.")
    return collection, search_ok


async def _fetch(run: _Run, sources: Sequence[Source]) -> dict[str, _Text]:
    settings = run.deps.settings.fetch
    fetcher = run.deps.fetcher
    texts: dict[str, _Text] = {}
    if fetcher is None or not settings.enabled:
        await run.step(Stage.FETCH, 1, 1)
        return texts
    to_fetch = list(sources[: settings.max_pages])
    semaphore = asyncio.Semaphore(settings.max_concurrency)
    done = 0

    async def fetch_one(source: Source) -> None:
        nonlocal done
        async with semaphore:
            body = await _fetch_text(fetcher, source)
        done += 1
        await run.step(Stage.FETCH, done, len(to_fetch))
        if body is None:
            return
        passages = relevant_passages(body.text, run.forms, settings.max_chars_per_source)
        if passages:
            source.fetched = True
            texts[source.id] = _Text(title=body.title, text=passages)

    await asyncio.gather(*(fetch_one(s) for s in to_fetch))
    await run.step(Stage.FETCH, 1, 1)
    return texts


async def _screen_subject(run: _Run) -> tuple[list[SanctionsListStatus], list[SanctionsMatch]]:
    deps = run.deps
    names = [run.subject.full_name, run.forms.short, run.forms.latin, run.subject.latin_name]
    lists = await deps.sanctions.lists()
    matches = await deps.sanctions.screen(
        [n for n in names if n], birth_date=run.subject.birth_date, entity_types=("person",)
    )
    if not lists:
        run.warnings.append("Санкционные списки не загружены: выполните «ipdl sanctions update».")
    else:
        hours = deps.settings.sanctions.stale_after_hours
        stale = [s.name for s in lists if _stale(s, hours, run.now)]
        if stale:
            run.warnings.append(f"Санкционные списки давно не обновлялись: {', '.join(stale)}.")
    if deps.jurisdictions.fatf_is_stale(run.now.date()):
        run.warnings.append(
            f"Перечни FATF в справочнике — на {deps.jurisdictions.fatf.as_of:%d.%m.%Y}: "
            "сверьте их с итогами последнего пленарного заседания FATF."
        )
    await run.step(Stage.SANCTIONS, 1, 1)
    return lists, matches


async def _extract(
    run: _Run, sources: Sequence[Source], texts: dict[str, _Text]
) -> tuple[list[SourceFacts], bool]:
    extractor = run.deps.extractor
    if extractor is None:
        run.warnings.append("ИИ-анализ источников отключён: факты не извлечены.")
        await run.step(Stage.EXTRACT, 1, 1)
        return [], False
    chosen = _choose_for_llm(sources, texts, run.deps.settings.llm.max_sources)
    extra = f"Уточнение аналитика: {run.subject.context}" if run.subject.context else ""
    if run.subject.birth_date:
        extra += f"\nДата рождения по данным аналитика: {run.subject.birth_date.isoformat()}"
    done = 0
    failures = 0

    async def analyze(source: Source, body: _Text) -> SourceFacts | None:
        nonlocal done, failures
        try:
            result: SourceFacts | None = await extractor.extract(
                source_id=source.id,
                text=body.text,
                title=body.title,
                domain=source.domain,
                name=run.subject.full_name,
                latin=run.forms.latin,
                extra=extra.strip(),
            )
        except LLMError as exc:
            failures += 1
            log.warning("llm_source_failed", source=source.id, error=str(exc)[:300])
            result = None
        done += 1
        await run.step(Stage.EXTRACT, done, len(chosen))
        return result

    results = await asyncio.gather(*(analyze(s, body) for s, body in chosen))
    facts: list[SourceFacts] = []
    for (source, _), result in zip(chosen, results, strict=True):
        if result is None:
            continue
        source.analyzed = True
        source.facts = 0 if result.about_subject == "no" else result.total
        facts.append(result)
    llm_used = bool(facts)
    if chosen and not llm_used:
        run.warnings.append("Языковая модель недоступна: факты из источников не извлечены.")
    elif failures:
        run.warnings.append(
            f"Языковая модель не обработала {failures} из {len(chosen)} источников."
        )
    await run.step(Stage.EXTRACT, 1, 1)
    return facts, llm_used


# ---------------------------------------------------------------- вспомогательное


def _source(index: int, candidate: Candidate, now: datetime) -> Source:
    return Source(
        id=f"S{index + 1}",
        url=candidate.url,
        title=candidate.title or candidate.domain,
        domain=candidate.domain,
        kind=candidate.kind,
        snippet=candidate.snippet[:600],
        published=candidate.published,
        retrieved_at=now,
        engines=sorted(candidate.engines),
        topics=sorted(candidate.topics),
        relevance=candidate.relevance,
    )


async def _fetch_text(fetcher: Fetcher, source: Source) -> _Text | None:
    try:
        document = await fetcher.fetch(source.url)
        extracted = await asyncio.to_thread(extract_text, document)
    except (FetchError, OSError, ValueError) as exc:
        log.info("fetch_skipped", url=source.url, reason=str(exc)[:200])
        return None
    except Exception as exc:  # noqa: BLE001 — ошибка разбора одной страницы не валит портрет
        log.warning("fetch_failed", url=source.url, error=f"{type(exc).__name__}: {exc}"[:300])
        return None
    if extracted is None:
        return None
    if extracted.published and source.published is None:
        source.published = extracted.published
    return _Text(title=extracted.title or source.title, text=extracted.text)


_RISK_TOPICS = frozenset({"sanctions", "legal", "adverse"})
_MAX_PER_DOMAIN = 2


def _choose_for_llm(
    sources: Sequence[Source], texts: dict[str, _Text], limit: int
) -> list[tuple[Source, _Text]]:
    """Источники для модели: по релевантности, но с разнообразием.

    Биографические страницы (энциклопедии, профили) ранжируются выше всего — без квоты модель
    увидела бы только их и пропустила расследования и санкции. Поэтому источники с «рисковыми»
    темами чередуются с остальными, а с одного домена берётся не больше двух страниц.
    Без загруженного текста используется сниппет поисковой выдачи.
    """
    candidates: list[tuple[Source, _Text]] = []
    for source in sources:
        body = texts.get(source.id)
        if body is None and len(source.snippet) >= 120:
            body = _Text(title=source.title, text=f"{source.title}\n{source.snippet}")
        if body is not None:
            candidates.append((source, body))
    risky = [c for c in candidates if _RISK_TOPICS & set(c[0].topics)]
    other = [c for c in candidates if not _RISK_TOPICS & set(c[0].topics)]
    chosen: list[tuple[Source, _Text]] = []
    per_domain: dict[str, int] = {}
    queues = [other, risky]
    turn = 0
    while len(chosen) < limit and (risky or other):
        queue = queues[turn % 2] or queues[(turn + 1) % 2]
        turn += 1
        source, body = queue.pop(0)
        if per_domain.get(source.domain, 0) >= _MAX_PER_DOMAIN:
            continue
        per_domain[source.domain] = per_domain.get(source.domain, 0) + 1
        chosen.append((source, body))
    return chosen


async def _screen_related(
    screener: SanctionsScreener, relations: Sequence[Relation], companies: Sequence[Company]
) -> list[SanctionsMatch]:
    matches: list[SanctionsMatch] = []
    targets = [(r.name, "person") for r in relations[:_RELATED_SCREEN_LIMIT]]
    targets += [(c.name, "entity") for c in companies[:_RELATED_SCREEN_LIMIT]]
    for name, entity_type in targets:
        found = await screener.screen([name], birth_date=None, entity_types=(entity_type,))
        matches.extend(m.model_copy(update={"query": name}) for m in found)
    return matches[:30]


def _stale(status: SanctionsListStatus, hours: int, now: datetime) -> bool:
    return status.fetched_at is None or (now - status.fetched_at).total_seconds() > hours * 3600
