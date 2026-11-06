"""Подставные зависимости для тестов пайплайна и API (без сети и без LLM)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from ipdl.analysis.model import SanctionsListStatus, SanctionsMatch


class FakeLLM:
    """LLM, которая отвечает заготовкой по подстроке в тексте промпта."""

    model = "fake-llm"

    def __init__(self, answers: dict[str, dict[str, Any]], *, fail_on: str | None = None) -> None:
        self.answers = answers
        self.fail_on = fail_on
        self.calls: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        from ipdl.llm.client import LLMError

        self.calls.append(user)
        if self.fail_on and self.fail_on in user:
            raise LLMError("модель недоступна")
        for marker, answer in self.answers.items():
            if marker in user:
                copy: dict[str, Any] = json.loads(json.dumps(answer))  # глубокая копия
                return copy
        return {"about_subject": "unclear"}

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class FakeScreener:
    def __init__(
        self,
        matches: dict[str, list[SanctionsMatch]] | None = None,
        lists: list[SanctionsListStatus] | None = None,
    ) -> None:
        self.matches = matches or {}
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        self._lists = (
            lists
            if lists is not None
            else [
                SanctionsListStatus(
                    id="un",
                    name="Сводный санкционный перечень СБ ООН",
                    published_at=datetime(2026, 10, 26, tzinfo=UTC),
                    fetched_at=datetime.now(UTC),
                    entries=1000,
                )
            ]
        )

    async def screen(
        self, names: Sequence[str], *, birth_date: date | None, entity_types: Sequence[str]
    ) -> list[SanctionsMatch]:
        self.calls.append((tuple(names), tuple(entity_types)))
        found: list[SanctionsMatch] = []
        for name in names:
            found.extend(self.matches.get(name, []))
        return found

    async def lists(self) -> list[SanctionsListStatus]:
        return self._lists


class FakeQueue:
    def __init__(self) -> None:
        self.portraits: list[uuid.UUID] = []
        self.sanctions_updates = 0

    async def enqueue_portrait(self, portrait_id: uuid.UUID) -> str:
        self.portraits.append(portrait_id)
        return f"portrait:{portrait_id}"

    async def enqueue_sanctions_update(self, *, force: bool = False) -> str:
        self.sanctions_updates += 1
        return "sanctions:update"

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def match(
    name: str,
    *,
    list_id: str = "un",
    ref: str = "TSi.001",
    score: float = 100,
    dob_match: bool | None = True,
) -> SanctionsMatch:
    return SanctionsMatch(
        list_id=list_id,
        list_name="Сводный санкционный перечень СБ ООН",
        entry_ref=ref,
        matched_name=name,
        primary_name=name,
        score=score,
        dob_match=dob_match,
    )
