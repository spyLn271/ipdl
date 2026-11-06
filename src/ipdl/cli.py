"""Командная строка: ``ipdl --help``."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ipdl import __version__
from ipdl.config.settings import get_settings

app = typer.Typer(
    help="IPDL — реестр и портреты иностранных публичных должностных лиц.", no_args_is_help=True
)
db_app = typer.Typer(help="Схема базы данных.", no_args_is_help=True)
users_app = typer.Typer(help="Пользователи.", no_args_is_help=True)
partners_app = typer.Typer(help="Зарубежные ПФР — партнёры по обмену.", no_args_is_help=True)
sanctions_app = typer.Typer(help="Санкционные списки.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(users_app, name="users")
app.add_typer(partners_app, name="partners")
app.add_typer(sanctions_app, name="sanctions")

console = Console()
err = Console(stderr=True)


@app.command()
def version() -> None:
    """Версия приложения."""
    console.print(__version__)


@app.command()
def serve(
    host: Annotated[str | None, typer.Option(help="Адрес (по умолчанию из настроек)")] = None,
    port: Annotated[int | None, typer.Option(help="Порт")] = None,
    reload: Annotated[bool, typer.Option(help="Перезапуск при изменении кода")] = False,
) -> None:
    """HTTP API (uvicorn)."""
    import uvicorn  # noqa: PLC0415

    settings = get_settings()
    uvicorn.run(
        "ipdl.api.app:create_app",
        factory=True,
        host=host or settings.api.host,
        port=port or settings.api.port,
        workers=1 if reload else settings.api.workers,
        reload=reload,
        proxy_headers=True,
        forwarded_allow_ips=settings.api.forwarded_allow_ips,
        server_header=False,
        log_config=None,
    )


@app.command()
def worker() -> None:
    """Воркер фоновых задач (построение портретов, обновление списков)."""
    from arq.worker import run_worker  # noqa: PLC0415

    from ipdl.api.worker import WorkerSettings  # noqa: PLC0415

    run_worker(WorkerSettings)  # type: ignore[arg-type]


# ---------------------------------------------------------------- база


@db_app.command("upgrade")
def db_upgrade(
    revision: Annotated[str, typer.Argument(help="Ревизия")] = "head",
    config: Annotated[Path, typer.Option(help="alembic.ini")] = Path("alembic.ini"),
) -> None:
    """Применить миграции."""
    from alembic import command  # noqa: PLC0415
    from alembic.config import Config  # noqa: PLC0415

    command.upgrade(Config(str(config)), revision)
    console.print(f"[green]Схема обновлена до {revision}[/green]")


# ---------------------------------------------------------------- пользователи


@users_app.command("create")
def users_create(
    username: Annotated[str, typer.Argument(help="Логин")],
    role: Annotated[str, typer.Option(help="admin | analyst | viewer | partner")] = "analyst",
    display_name: Annotated[str | None, typer.Option(help="Имя для журнала")] = None,
    partner_id: Annotated[str | None, typer.Option(help="ID партнёра (для роли partner)")] = None,
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Прочитать пароль из stdin (для скриптов)")
    ] = False,
    exist_ok: Annotated[
        bool,
        typer.Option(
            "--exist-ok",
            help="Если пользователь есть — привести его роль и пароль к заданным",
        ),
    ] = False,
) -> None:
    """Создать пользователя (пароль спрашивается без отображения)."""
    import uuid  # noqa: PLC0415
    from datetime import UTC, datetime  # noqa: PLC0415

    from sqlalchemy import select  # noqa: PLC0415

    from ipdl.auth.service import (  # noqa: PLC0415
        PasswordPolicyError,
        hash_password,
        normalize_username,
        revoke_user_sessions,
        verify_password,
    )
    from ipdl.db.models import Role, User  # noqa: PLC0415
    from ipdl.db.session import Database  # noqa: PLC0415

    settings = get_settings()
    try:
        role_value = Role(role)
    except ValueError:
        err.print(f"[red]Неизвестная роль: {role}[/red]")
        raise typer.Exit(2) from None
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = typer.prompt("Пароль", hide_input=True, confirmation_prompt=True)
    try:
        password_hash = hash_password(password, settings.auth)
    except PasswordPolicyError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    login = normalize_username(username)
    partner = uuid.UUID(partner_id) if partner_id else None

    async def create() -> tuple[str, str] | None:
        db = Database(settings.db)
        try:
            async with db.session() as session:
                user = await session.scalar(select(User).where(User.username == login))
                if user is None:
                    user = User(
                        username=login,
                        display_name=display_name or username,
                        password_hash=password_hash,
                        role=role_value,
                        partner_id=partner,
                    )
                    session.add(user)
                    await session.flush()
                    return str(user.id), "создан"
                if not exist_ok:
                    return None
                # Пароль меняется (и сессии отзываются), только если он действительно другой:
                # повторный запуск при каждом старте стека не выбивает уже вошедший сервис
                if not verify_password(password, user.password_hash):
                    user.password_hash = password_hash
                    user.password_changed_at = datetime.now(UTC)
                    await revoke_user_sessions(session, user.id)
                user.role = role_value
                user.is_active = True
                user.failed_logins = 0
                user.locked_until = None
                if display_name:
                    user.display_name = display_name
                if partner is not None:
                    user.partner_id = partner
                return str(user.id), "обновлён"
        finally:
            await db.dispose()

    result = asyncio.run(create())
    if result is None:
        err.print(f"[red]Пользователь {login} уже существует (--exist-ok — обновить)[/red]")
        raise typer.Exit(1)
    user_id, action = result
    console.print(f"[green]Пользователь {login} ({role_value.value}) {action}: {user_id}[/green]")


@users_app.command("list")
def users_list() -> None:
    """Список пользователей."""
    from sqlalchemy import select  # noqa: PLC0415

    from ipdl.db.models import User  # noqa: PLC0415
    from ipdl.db.session import Database  # noqa: PLC0415

    async def load() -> list[User]:
        db = Database(get_settings().db)
        try:
            async with db.session() as session:
                return list((await session.scalars(select(User).order_by(User.username))).all())
        finally:
            await db.dispose()

    table = Table("Логин", "Имя", "Роль", "Активен", "Последний вход")
    for user in asyncio.run(load()):
        table.add_row(
            user.username,
            user.display_name,
            user.role.value,
            "да" if user.is_active else "нет",
            f"{user.last_login_at:%d.%m.%Y %H:%M}" if user.last_login_at else "—",
        )
    console.print(table)


# ---------------------------------------------------------------- партнёры


@partners_app.command("add")
def partners_add(
    country: Annotated[str, typer.Option(help="Код страны ISO 3166-1 alpha-2")],
    name: Annotated[str, typer.Option(help="Наименование ПФР")],
    contact: Annotated[str | None, typer.Option(help="Контакты")] = None,
) -> None:
    """Добавить зарубежное ПФР."""
    from ipdl.db.models import Partner  # noqa: PLC0415
    from ipdl.db.session import Database  # noqa: PLC0415

    async def add() -> str:
        db = Database(get_settings().db)
        try:
            async with db.session() as session:
                partner = Partner(country=country.upper(), name=name, contact=contact)
                session.add(partner)
                await session.flush()
                return str(partner.id)
        finally:
            await db.dispose()

    console.print(f"[green]Партнёр добавлен: {asyncio.run(add())}[/green]")


# ---------------------------------------------------------------- санкции


@sanctions_app.command("update")
def sanctions_update(
    force: Annotated[bool, typer.Option(help="Перезагрузить, даже если файл не изменился")] = False,
) -> None:
    """Загрузить официальные санкционные списки (ООН, OFAC, ЕС, Великобритания)."""
    from ipdl.db.session import Database  # noqa: PLC0415
    from ipdl.logs import configure_logging  # noqa: PLC0415
    from ipdl.sanctions.service import SanctionsUpdater, UpdateResult  # noqa: PLC0415

    settings = get_settings()
    configure_logging(settings.log)

    async def run() -> list[UpdateResult]:
        db = Database(settings.db)
        try:
            return await SanctionsUpdater(db, settings.sanctions).update_all(force=force)
        finally:
            await db.dispose()

    results = asyncio.run(run())
    table = Table("Список", "Результат", "Записей", "Ошибка")
    for result in results:
        table.add_row(result.list_id, result.status, str(result.entries), result.error or "")
    console.print(table)
    if any(r.status == "error" for r in results):
        raise typer.Exit(1)


@sanctions_app.command("search")
def sanctions_search(
    name: Annotated[str, typer.Argument(help="Имя (любой алфавит)")],
    birth_date: Annotated[
        str | None, typer.Option("--dob", help="Дата рождения ГГГГ-ММ-ДД")
    ] = None,
    entity: Annotated[bool, typer.Option(help="Искать среди компаний")] = False,
) -> None:
    """Проверить имя по загруженным спискам."""
    from ipdl.analysis.model import SanctionsMatch  # noqa: PLC0415
    from ipdl.db.session import Database  # noqa: PLC0415
    from ipdl.sanctions.service import DbScreener  # noqa: PLC0415

    settings = get_settings()

    async def run() -> list[SanctionsMatch]:
        db = Database(settings.db)
        try:
            return await DbScreener(db, settings.sanctions).screen(
                [name],
                birth_date=date.fromisoformat(birth_date) if birth_date else None,
                entity_types=("entity",) if entity else ("person",),
            )
        finally:
            await db.dispose()

    matches = asyncio.run(run())
    if not matches:
        console.print("Совпадений не найдено.")
        return
    table = Table("Список", "Запись", "Имя в списке", "Сходство", "Дата рождения", "Программы")
    for m in matches:
        dob = "совпадает" if m.dob_match is True else "отличается" if m.dob_match is False else "—"
        table.add_row(
            m.list_name,
            m.entry_ref,
            m.matched_name,
            f"{m.score:.0f}",
            dob,
            ", ".join(m.programs)[:60],
        )
    console.print(table)


# ---------------------------------------------------------------- портрет без реестра


@app.command()
def portrait(
    full_name: Annotated[str, typer.Argument(help="ФИО")],
    latin: Annotated[str | None, typer.Option(help="Написание латиницей")] = None,
    birth_date: Annotated[
        str | None, typer.Option("--dob", help="Дата рождения ГГГГ-ММ-ДД")
    ] = None,
    citizenship: Annotated[str | None, typer.Option(help="Гражданство, ISO-код")] = None,
    context: Annotated[str | None, typer.Option(help="Уточнение: компания, должность")] = None,
    out: Annotated[Path | None, typer.Option(help="Сохранить портрет в JSON")] = None,
    docx_out: Annotated[
        Path | None, typer.Option("--docx", help="Сохранить портрет в DOCX")
    ] = None,
) -> None:
    """Построить портрет без записи в реестр (для проверки настроек и методики)."""
    from ipdl.analysis.methodology import load_jurisdictions, load_risk_model  # noqa: PLC0415
    from ipdl.analysis.model import Portrait, Subject  # noqa: PLC0415
    from ipdl.analysis.pipeline import Deps, Stage, build_portrait  # noqa: PLC0415
    from ipdl.db.session import Database  # noqa: PLC0415
    from ipdl.fetch.fetcher import Fetcher  # noqa: PLC0415
    from ipdl.llm.client import create_llm_client  # noqa: PLC0415
    from ipdl.llm.extract import FactExtractor  # noqa: PLC0415
    from ipdl.logs import configure_logging  # noqa: PLC0415
    from ipdl.report.render import render_docx  # noqa: PLC0415
    from ipdl.sanctions.service import DbScreener  # noqa: PLC0415
    from ipdl.search.collect import load_plan  # noqa: PLC0415
    from ipdl.search.searxng import SearxngClient  # noqa: PLC0415

    settings = get_settings()
    configure_logging(settings.log)
    subject = Subject(
        full_name=full_name,
        latin_name=latin,
        birth_date=date.fromisoformat(birth_date) if birth_date else None,
        citizenship=citizenship.upper() if citizenship else None,
        context=context,
    )

    async def run() -> Portrait:
        db = Database(settings.db)
        llm = create_llm_client(settings.llm) if settings.llm.enabled else None
        searxng, fetcher = SearxngClient(settings.search), Fetcher(settings.fetch)
        deps = Deps(
            settings=settings,
            plan=load_plan(settings.search.queries_file),
            model=load_risk_model(settings.methodology_file),
            jurisdictions=load_jurisdictions(settings.jurisdictions_file),
            searxng=searxng,
            fetcher=fetcher,
            extractor=FactExtractor(llm) if llm else None,
            sanctions=DbScreener(db, settings.sanctions),
        )

        async def progress(stage: Stage, percent: int) -> None:
            err.print(f"[dim]{stage.value:9} {percent:3d}%[/dim]")

        try:
            return await build_portrait(subject, deps, progress)
        finally:
            if llm is not None:
                await llm.aclose()
            await searxng.aclose()
            await fetcher.aclose()
            await db.dispose()

    result = asyncio.run(run())
    if out:
        out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    if docx_out:
        docx_out.write_bytes(render_docx(result, review=None, org=settings.org, version=0))
    console.print(
        f"[bold]{result.identity.full_name}[/bold]: {result.pep.category.value}, "
        f"риск {result.risk.score}/100 ({result.risk.level.value})"
    )
    console.print(result.conclusion)
    for warning in result.warnings:
        err.print(f"[yellow]{warning}[/yellow]")


@app.command("methodology")
def methodology_check() -> None:
    """Проверить методику и справочники (YAML) без запуска сервисов."""
    from ipdl.analysis.methodology import load_jurisdictions, load_risk_model  # noqa: PLC0415
    from ipdl.sanctions.service import load_sources  # noqa: PLC0415
    from ipdl.search.collect import load_plan  # noqa: PLC0415

    settings = get_settings()
    model = load_risk_model(settings.methodology_file)
    jurisdictions = load_jurisdictions(settings.jurisdictions_file)
    plan = load_plan(settings.search.queries_file)
    sources = load_sources(settings.sanctions.sources_file)
    weights = sum(f.weight for f in model.factors.values())
    console.print(
        json.dumps(
            {
                "method": model.id,
                "weights_sum": round(weights, 3),
                "fatf_as_of": jurisdictions.fatf.as_of.isoformat(),
                "queries": len(plan.queries),
                "sanctions_lists": [s.id for s in sources],
            },
            ensure_ascii=False,
        )
    )
    if abs(weights - 1) > 1e-6:
        err.print("[red]Сумма весов факторов должна быть 1.0[/red]")
        sys.exit(1)
