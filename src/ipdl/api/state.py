"""Состояние приложения, общее для всех запросов (``app.state.ipdl``)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from ipdl.analysis.methodology import (
    Jurisdictions,
    RiskModel,
    load_jurisdictions,
    load_risk_model,
)
from ipdl.api.jobs import JobQueue
from ipdl.config.settings import Settings
from ipdl.db.session import Database
from ipdl.sanctions.service import SanctionsSource, load_sources


@dataclass
class AppState:
    settings: Settings
    db: Database
    queue: JobQueue

    @cached_property
    def risk_model(self) -> RiskModel:
        return load_risk_model(self.settings.methodology_file)

    @cached_property
    def jurisdictions(self) -> Jurisdictions:
        return load_jurisdictions(self.settings.jurisdictions_file)

    @cached_property
    def sanctions_sources(self) -> list[SanctionsSource]:
        return load_sources(self.settings.sanctions.sources_file)
