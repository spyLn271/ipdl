"""Настройки приложения.

Источники в порядке приоритета (сильнее → слабее): аргументы конструктора →
переменные окружения ``IPDL_*`` → ``.env`` → ``config.yaml`` → значения по умолчанию.

Вложенные поля переопределяются через ``__``: ``IPDL_LLM__MODEL=qwen3:4b``.
Путь к YAML задаётся переменной ``IPDL_CONFIG_FILE`` (по умолчанию ``./config.yaml``).
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_FILE_ENV = "IPDL_CONFIG_FILE"
DEFAULT_CONFIG_FILE = Path("config.yaml")


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class LLMProvider(StrEnum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"  # vLLM, llama.cpp server, LM Studio


class LogSettings(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_format: bool = False


class DatabaseSettings(BaseModel):
    url: SecretStr = SecretStr("postgresql+asyncpg://ipdl:ipdl@localhost:5432/ipdl")
    pool_size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    echo: bool = False


class SearchSettings(BaseModel):
    """Поиск открытых источников через SearXNG (JSON API)."""

    base_url: str = "http://localhost:8080"
    timeout_s: float = Field(default=20, gt=0)
    # Одновременных запросов к SearXNG: он сам опрашивает несколько поисковиков на запрос
    max_concurrency: int = Field(default=2, ge=1)
    # Интервал между стартами запросов — поисковики ограничивают частоту
    stagger_s: float = Field(default=0.6, ge=0, le=10)
    max_results_per_query: int = Field(default=20, ge=1, le=100)
    max_sources: int = Field(default=40, ge=1, le=300)
    queries_file: Path = Path("methodology/search-queries.yaml")


class FetchSettings(BaseModel):
    """Загрузка найденных страниц для извлечения текста."""

    enabled: bool = True
    timeout_s: float = Field(default=12, gt=0)
    max_bytes: int = Field(default=3_000_000, ge=10_000)
    max_pages: int = Field(default=16, ge=0, le=100)
    max_concurrency: int = Field(default=6, ge=1)
    max_redirects: int = Field(default=5, ge=0, le=10)
    respect_robots_txt: bool = True
    # Wikimedia и ряд сайтов требуют контакт в User-Agent (https://w.wiki/4wJS)
    user_agent: str = (
        "IPDL/0.1 (+https://github.com/yelnur-nazarbayev/IpdlCloude; AML/KYC research)"
    )
    # Сколько символов текста вокруг упоминаний лица оставлять на источник
    max_chars_per_source: int = Field(default=3500, ge=500)


class LLMSettings(BaseModel):
    enabled: bool = True
    provider: LLMProvider = LLMProvider.OLLAMA
    base_url: str = "http://localhost:11434"
    model: str = "qwen3:8b"
    api_key: SecretStr | None = None
    temperature: float = Field(default=0.1, ge=0, le=2)
    num_ctx: int = Field(default=8192, ge=512)
    think: bool = False
    keep_alive: str = "30m"
    timeout_s: float = Field(default=300, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_concurrency: int = Field(default=2, ge=1)
    # Сколько самых релевантных источников передавать модели (на CPU ~30 с на источник)
    max_sources: int = Field(default=10, ge=1, le=60)
    # Логи промптов содержат персональные данные — включать только для отладки
    log_dir: Path | None = None


class SanctionsSettings(BaseModel):
    sources_file: Path = Path("methodology/sanctions-sources.yaml")
    timeout_s: float = Field(default=180, gt=0)
    max_bytes: int = Field(default=200_000_000, ge=1_000_000)
    # Порог «возможного совпадения» (0–100) по сходству имени
    match_threshold: float = Field(default=88, ge=50, le=100)
    max_matches: int = Field(default=20, ge=1, le=200)
    # Ежедневное обновление списков воркером (UTC)
    update_hour_utc: int = Field(default=3, ge=0, le=23)
    stale_after_hours: int = Field(default=48, ge=1)


class JobSettings(BaseModel):
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "ipdl:jobs"
    max_concurrency: int = Field(default=2, ge=1)
    max_pending: int = Field(default=50, ge=1)
    timeout_s: float = Field(default=1800, gt=0)


class AuthSettings(BaseModel):
    session_cookie: str = "ipdl_session"
    csrf_cookie: str = "ipdl_csrf"
    csrf_header: str = "X-CSRF-Token"
    session_ttl_hours: int = Field(default=12, ge=1, le=720)
    # Secure-cookie: в продакшене сайт работает только по HTTPS
    cookie_secure: bool = True
    max_failed_logins: int = Field(default=5, ge=1)
    lockout_minutes: int = Field(default=15, ge=1)
    min_password_length: int = Field(default=12, ge=8)


class OrgSettings(BaseModel):
    """Реквизиты, которые попадают в шапку интерфейса и в экспорт."""

    system_name: str = "IPDL"
    home_country: str = Field(default="KZ", min_length=2, max_length=2)
    authority: str = "Подразделение финансовой разведки"
    legal_notice: str = (
        "Информация предоставляется в рамках международного обмена между подразделениями "
        "финансовой разведки и предназначена только для служебного использования. "
        "Не является основанием для обвинения."
    )


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)
    root_path: str = ""
    docs_enabled: bool = False
    metrics_enabled: bool = True
    # IP-адреса прокси, которым разрешено передавать X-Forwarded-For
    forwarded_allow_ips: str = "127.0.0.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="IPDL_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        validate_default=True,
    )

    env: Environment = Environment.DEV
    log: LogSettings = Field(default_factory=LogSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    fetch: FetchSettings = Field(default_factory=FetchSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    sanctions: SanctionsSettings = Field(default_factory=SanctionsSettings)
    jobs: JobSettings = Field(default_factory=JobSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    org: OrgSettings = Field(default_factory=OrgSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    methodology_file: Path = Path("methodology/risk-model.yaml")
    jurisdictions_file: Path = Path("methodology/jurisdictions.yaml")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_path = Path(os.environ.get(CONFIG_FILE_ENV, DEFAULT_CONFIG_FILE))
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        ]
        if yaml_path.is_file():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path))
        return tuple(sources)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Кэшированный экземпляр настроек процесса."""
    return Settings()
