.PHONY: install lint format typecheck test test-db check serve worker web migrate sanctions up down

TEST_DB ?= postgresql+asyncpg://ipdl:ipdl@localhost:5432/ipdl_test

install:            ## зависимости и pre-commit
	uv sync
	uv run pre-commit install

lint:               ## ruff: линтер и форматирование
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test:               ## модульные тесты (без PostgreSQL)
	uv run pytest --cov

test-db:            ## все тесты, включая интеграционные с PostgreSQL
	IPDL_TEST_DATABASE_URL=$(TEST_DB) uv run pytest --cov

check: lint typecheck test

migrate:
	uv run ipdl db upgrade

sanctions:          ## загрузить санкционные списки
	uv run ipdl sanctions update

serve:
	uv run ipdl serve --reload

worker:
	uv run ipdl worker

web:
	cd web && pnpm dev

up:                 ## весь стек в Docker
	docker compose up -d --build

down:
	docker compose down
