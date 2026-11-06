"""Метрики Prometheus (``GET /metrics``)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

PORTRAITS_TOTAL = Counter("ipdl_portraits_total", "Построенные портреты", ["status"])
PORTRAIT_DURATION = Histogram(
    "ipdl_portrait_duration_seconds",
    "Длительность построения портрета",
    buckets=(10, 30, 60, 120, 300, 600, 900, 1200, 1800),
)
PORTRAITS_IN_PROGRESS = Gauge("ipdl_portraits_in_progress", "Портреты в работе")
SANCTIONS_UPDATES = Counter(
    "ipdl_sanctions_updates_total", "Обновления списков", ["list", "status"]
)
LOGINS = Counter("ipdl_logins_total", "Попытки входа", ["result"])
HTTP_DURATION = Histogram(
    "ipdl_http_request_duration_seconds",
    "Длительность HTTP-запросов",
    ["method", "route", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
