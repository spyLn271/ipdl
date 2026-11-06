"""Загрузка методики оценки риска и справочника юрисдикций из ``methodology/*.yaml``."""

from __future__ import annotations

from datetime import date
from functools import cache
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ipdl.analysis.model import FactorKey, RiskLevel


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FactorSpec(_Model):
    weight: float = Field(gt=0, le=1)
    title: str


class Floor(_Model):
    min_score: int = Field(ge=0, le=100)
    reason: str


class RiskModel(_Model):
    id: str
    title: str
    bands: dict[RiskLevel, tuple[int, int]]
    points: dict[RiskLevel, float]
    no_data_points: float = Field(ge=0, le=100)
    review_months: dict[RiskLevel, int]
    factors: dict[FactorKey, FactorSpec]
    floors: dict[str, Floor]
    legal_basis: dict[str, Any]

    @model_validator(mode="after")
    def _check(self) -> RiskModel:
        missing = set(FactorKey) - set(self.factors)
        if missing:
            raise ValueError(f"в методике нет факторов: {sorted(missing)}")
        levels = {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH}
        if set(self.bands) != levels or set(self.points) != levels:
            raise ValueError("bands и points задаются для low, medium, high")
        edges = sorted(self.bands.values())
        if edges[0][0] != 0 or edges[-1][1] != 100:
            raise ValueError("bands должны покрывать 0–100")
        for (_, prev_end), (start, _) in pairwise(edges):
            if start != prev_end + 1:
                raise ValueError("bands должны идти подряд без пропусков")
        return self

    def level_for(self, score: int) -> RiskLevel:
        for level, (low, high) in self.bands.items():
            if low <= score <= high:
                return level
        return RiskLevel.HIGH

    @property
    def measures(self) -> list[str]:
        return list(self.legal_basis.get("pep_measures", {}).get("measures", []))


class FatfLists(_Model):
    as_of: date
    review_after_days: int = 130
    source: str
    source_url: str
    call_for_action: dict[str, str]
    increased_monitoring: list[str]


class PreferentialTax(_Model):
    as_of: date
    source: str
    source_url: str
    codes: list[str]
    partial: dict[str, str] = Field(default_factory=dict)


class Jurisdictions(_Model):
    fatf: FatfLists
    preferential_tax: PreferentialTax
    national_high_risk: dict[str, str] = Field(default_factory=dict)

    def fatf_is_stale(self, today: date) -> bool:
        return (today - self.fatf.as_of).days > self.fatf.review_after_days


@cache
def load_risk_model(path: Path) -> RiskModel:
    return RiskModel.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@cache
def load_jurisdictions(path: Path) -> Jurisdictions:
    return Jurisdictions.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
