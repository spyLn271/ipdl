# syntax=docker/dockerfile:1.7
# Образ API и воркера IPDL: `docker build -t ipdl/api .`

ARG PYTHON_IMAGE=python:3.12.14-slim-trixie

FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

# ---------------------------------------------------------------- зависимости и пакет
FROM ${PYTHON_IMAGE} AS builder
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------- runtime
FROM ${PYTHON_IMAGE} AS runtime
# pango/harfbuzz — WeasyPrint (экспорт PDF); шрифты с кириллицей и казахскими буквами
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tini libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
        fonts-inter fonts-dejavu-core fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app methodology ./methodology
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app alembic.ini config.yaml ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/app \
    IPDL_ENV=prod \
    IPDL_LOG__JSON_FORMAT=true \
    IPDL_API__HOST=0.0.0.0 \
    IPDL_API__PORT=8000

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
ENTRYPOINT ["tini", "--", "ipdl"]
CMD ["serve"]
