from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import respx
from typer.testing import CliRunner

from ipdl import __version__
from ipdl.cli import app
from ipdl.config.settings import get_settings
from ipdl.db.session import Database
from tests.conftest import ROOT, TEST_DB_ENV
from tests.integration.test_sanctions_db import mock_lists

runner = CliRunner()


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.chdir(ROOT)
    if url := os.environ.get(TEST_DB_ENV):
        monkeypatch.setenv("IPDL_DB__URL", url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_version_and_methodology(cli_env: None) -> None:
    assert runner.invoke(app, ["version"]).stdout.strip() == __version__
    result = runner.invoke(app, ["methodology"])
    assert result.exit_code == 0, result.output
    assert '"weights_sum": 1.0' in result.stdout
    assert '"sanctions_lists": ["un", "ofac_sdn", "eu", "uk"]' in result.stdout


@pytest.mark.db
def test_users_partners_and_sanctions(cli_env: None, clean_db: Database) -> None:
    weak = runner.invoke(
        app, ["users", "create", "boss", "--role", "admin"], input="short\nshort\n"
    )
    assert weak.exit_code == 2
    bad_role = runner.invoke(app, ["users", "create", "boss", "--role", "king"])
    assert bad_role.exit_code == 2
    created = runner.invoke(
        app,
        ["users", "create", "Boss", "--role", "admin", "--display-name", "Начальник"],
        input="very-long-password-1\nvery-long-password-1\n",
    )
    assert created.exit_code == 0, created.output
    listed = runner.invoke(app, ["users", "list"])
    assert "boss" in listed.stdout and "admin" in listed.stdout

    # Служебная учётная запись из скрипта: пароль из stdin, повторный запуск не падает
    duplicate = runner.invoke(
        app, ["users", "create", "boss", "--password-stdin"], input="very-long-password-1\n"
    )
    assert duplicate.exit_code == 1 and "уже существует" in duplicate.output
    for _ in range(2):
        ensured = runner.invoke(
            app,
            ["users", "create", "svc", "--role", "analyst", "--password-stdin", "--exist-ok"],
            input="service-password-123\n",
        )
        assert ensured.exit_code == 0, ensured.output
    assert "обновлён" in ensured.stdout
    demoted = runner.invoke(
        app,
        ["users", "create", "boss", "--role", "viewer", "--password-stdin", "--exist-ok"],
        input="another-password-12\n",
    )
    assert demoted.exit_code == 0, demoted.output
    listed = runner.invoke(app, ["users", "list"])
    assert "svc" in listed.stdout and "viewer" in listed.stdout

    partner = runner.invoke(
        app, ["partners", "add", "--country", "uz", "--name", "ПФР Узбекистана"]
    )
    assert partner.exit_code == 0 and "Партнёр добавлен" in partner.stdout

    with respx.mock() as router:
        mock_lists(router)
        update = runner.invoke(app, ["sanctions", "update"])
    assert update.exit_code == 0, update.output
    assert "updated" in update.stdout

    found = runner.invoke(app, ["sanctions", "search", "Виктор Тестман", "--dob", "1958-05-26"])
    assert found.exit_code == 0
    assert "TESTMAN" in found.stdout and "совпадает" in found.stdout
    nothing = runner.invoke(app, ["sanctions", "search", "Тимур Турлов"])
    assert "Совпадений не найдено" in nothing.stdout
    entity = runner.invoke(app, ["sanctions", "search", "Northwind Trading", "--entity"])
    assert "NORTHWIND" in entity.stdout.upper()
