from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from ipdl.analysis.model import Portrait
from ipdl.api.registry import effective_portrait, refresh_person
from ipdl.auth.service import hash_password
from ipdl.db.models import JobStatus, Partner, Person, Role, User
from ipdl.db.models import Portrait as PortraitRow
from ipdl.db.session import Database
from tests.conftest import make_settings
from tests.sample import build_sample

pytestmark = pytest.mark.db

PASSWORD = "correct-horse-battery-1"
_SAMPLE: dict[str, Portrait] = {}


async def sample_portrait() -> Portrait:
    if "p" not in _SAMPLE:
        _SAMPLE["p"] = await build_sample(make_settings())
    return _SAMPLE["p"]


async def add_user(
    db: Database, username: str, role: Role, partner_id: uuid.UUID | None = None
) -> uuid.UUID:
    async with db.session() as session:
        user = User(
            username=username,
            display_name=username.title(),
            password_hash=hash_password(PASSWORD, make_settings().auth),
            role=role,
            partner_id=partner_id,
        )
        session.add(user)
        await session.flush()
        return user.id


async def add_partner(
    db: Database, country: str = "UZ", name: str = "ПФР Узбекистана"
) -> uuid.UUID:
    async with db.session() as session:
        partner = Partner(country=country, name=name)
        session.add(partner)
        await session.flush()
        return partner.id


@asynccontextmanager
async def client_for(app: Any, username: str) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as client:
        response = await client.post(
            "/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        client.headers["X-CSRF-Token"] = client.cookies["ipdl_csrf"]
        yield client


async def store_done_portrait(db: Database, app: Any, person_id: str) -> uuid.UUID:
    """Записать готовый портрет (как это сделал бы воркер)."""
    portrait = await sample_portrait()
    async with db.session() as session:
        row = (
            await session.scalars(
                select(PortraitRow)
                .where(PortraitRow.person_id == uuid.UUID(person_id))
                .order_by(PortraitRow.version.desc())
            )
        ).first()
        assert row is not None
        row.status, row.progress, row.stage = JobStatus.DONE, 100, "assess"
        row.data = portrait.model_dump(mode="json")
        row.finished_at = datetime.now(UTC)
        person = await session.get(Person, row.person_id)
        assert person is not None
        refresh_person(person, row, effective_portrait(row, app.state.ipdl))  # type: ignore[arg-type]
        return row.id


# ---------------------------------------------------------------- вход


async def test_login_logout_and_lockout(api: tuple[httpx.AsyncClient, Any]) -> None:
    client, app = api
    db: Database = app.state.ipdl.db
    await add_user(db, "analyst", Role.ANALYST)

    meta = await client.get("/api/v1/meta")
    assert meta.status_code == 200 and meta.json()["home_country"] == "KZ"
    assert (await client.get("/api/v1/persons")).status_code == 401

    bad = await client.post("/api/v1/auth/login", json={"username": "analyst", "password": "nope"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"
    unknown = await client.post(
        "/api/v1/auth/login", json={"username": "ghost", "password": "nope"}
    )
    assert unknown.json()["error"]["code"] == "invalid_credentials"

    ok = await client.post(
        "/api/v1/auth/login", json={"username": " Analyst ", "password": PASSWORD}
    )
    assert ok.status_code == 200
    assert "httponly" in ok.headers.get_list("set-cookie")[0].lower()
    assert ok.headers["cache-control"] == "no-store"
    me = await client.get("/api/v1/auth/me")
    assert me.json()["user"]["role"] == "analyst"

    # Без CSRF-заголовка изменяющие запросы отклоняются
    no_csrf = await client.post("/api/v1/persons", json={"full_name": "Тест Тестович"})
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "csrf_failed"

    out = await client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies["ipdl_csrf"]}
    )
    assert out.status_code == 204
    client.cookies.clear()
    assert (await client.get("/api/v1/auth/me")).status_code == 401

    for _ in range(5):
        await client.post("/api/v1/auth/login", json={"username": "analyst", "password": "wrong"})
    locked = await client.post(
        "/api/v1/auth/login", json={"username": "analyst", "password": PASSWORD}
    )
    assert locked.json()["error"]["code"] == "locked"

    audit = await _audit(db)
    assert {"login", "login_failed", "logout"} <= audit


async def _audit(db: Database) -> set[str]:
    from ipdl.db.models import AuditEvent

    async with db.session() as session:
        return set((await session.scalars(select(AuditEvent.action))).all())


async def test_password_change(api: tuple[httpx.AsyncClient, Any]) -> None:
    _, app = api
    await add_user(app.state.ipdl.db, "viewer", Role.VIEWER)
    async with client_for(app, "viewer") as client:
        weak = await client.post(
            "/auth/password", json={"current_password": PASSWORD, "new_password": "short-pass"}
        )
        assert weak.status_code == 422
        wrong = await client.post(
            "/auth/password", json={"current_password": "x", "new_password": "a-much-longer-pass-1"}
        )
        assert wrong.status_code == 400
        done = await client.post(
            "/auth/password",
            json={"current_password": PASSWORD, "new_password": "a-much-longer-pass-1"},
        )
        assert done.status_code == 204
        # Все сессии отозваны
        assert (await client.get("/auth/me")).status_code == 401


# ---------------------------------------------------------------- реестр и портреты


async def test_registry_flow(api: tuple[httpx.AsyncClient, Any]) -> None:
    _, app = api
    db: Database = app.state.ipdl.db
    queue = app.state.ipdl.queue
    await add_user(db, "analyst", Role.ANALYST)
    await add_user(db, "viewer", Role.VIEWER)

    async with client_for(app, "analyst") as analyst, client_for(app, "viewer") as viewer:
        assert (await viewer.post("/persons", json={"full_name": "Иванов Пётр"})).status_code == 403

        invalid = await analyst.post("/persons", json={"full_name": "Ив", "citizenship": "Belarus"})
        assert invalid.status_code == 422

        created = await analyst.post(
            "/persons",
            json={
                "full_name": "Иванов Пётр Сергеевич",
                "birth_date": "1970-03-05",
                "citizenship": "by",
                "latin_name": "",
            },
        )
        assert created.status_code == 201, created.text
        person = created.json()
        assert person["citizenship"] == "BY" and person["latin_name"] is None
        assert person["latest"]["status"] == "queued"
        assert len(queue.portraits) == 1

        again = await analyst.post(f"/persons/{person['id']}/portraits")
        assert again.status_code == 409

        found = await viewer.get("/persons", params={"q": "Pyotr Ivanov"})
        assert found.json()["total"] == 1
        assert (await viewer.get("/persons", params={"q": "Сидоров"})).json()["total"] == 0

        portrait_id = await store_done_portrait(db, app, person["id"])
        detail = (await viewer.get(f"/persons/{person['id']}")).json()
        assert detail["can_edit"] is False
        assert detail["person"]["pep_category"] == "foreign"
        assert detail["person"]["risk_level"] == "high"
        assert detail["current"]["portrait"]["pep"]["category"] == "foreign"
        assert detail["versions"][0]["score"] >= 85

        filtered = await viewer.get("/persons", params={"pep": "foreign", "level": "high"})
        assert filtered.json()["total"] == 1

        # Решение аналитика: фактор «Финансовые операции» и проверка источника
        review = await analyst.put(
            f"/portraits/{portrait_id}/review",
            json={
                "factors": {"transactions": {"level": "high", "comment": "Три СПО за 2026 год"}},
                "sources": {"S1": "confirmed"},
                "conclusion": "Отношения не устанавливать до получения ответа ПФР.",
            },
        )
        assert review.status_code == 200, review.text
        body = review.json()
        factor = next(f for f in body["portrait"]["risk"]["factors"] if f["key"] == "transactions")
        assert factor["level"] == "high" and factor["overridden"]
        assert body["review"]["reviewer"] == "Analyst"
        assert body["portrait"]["conclusion"].startswith("Отношения не устанавливать")
        bad_source = await analyst.put(
            f"/portraits/{portrait_id}/review", json={"sources": {"S99": "confirmed"}}
        )
        assert bad_source.status_code == 422
        assert (await viewer.put(f"/portraits/{portrait_id}/review", json={})).status_code == 403

        docx = await viewer.get(f"/portraits/{portrait_id}/export.docx")
        assert docx.status_code == 200
        assert docx.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert "filename*=UTF-8''" in docx.headers["content-disposition"]
        pdf = await viewer.get(f"/portraits/{portrait_id}/export.pdf")
        assert pdf.content.startswith(b"%PDF")
        assert (await viewer.get(f"/portraits/{portrait_id}/export.xlsx")).status_code == 404

        updated = await analyst.patch(
            f"/persons/{person['id']}", json={"context": "Минфин Беларуси"}
        )
        assert updated.json()["context"] == "Минфин Беларуси"

        rebuilt = await analyst.post(f"/persons/{person['id']}/portraits")
        assert rebuilt.status_code == 202 and rebuilt.json()["version"] == 2
        polled = await viewer.get(f"/portraits/{rebuilt.json()['id']}")
        assert polled.json()["meta"]["status"] == "queued" and polled.json()["portrait"] is None
        made_current = await analyst.post(f"/portraits/{rebuilt.json()['id']}/current")
        assert made_current.status_code == 409

        assert (await analyst.delete(f"/persons/{person['id']}")).status_code == 403
        assert (await viewer.get(f"/persons/{uuid.uuid4()}")).status_code == 404


async def test_queue_limit(api: tuple[httpx.AsyncClient, Any]) -> None:
    _, app = api
    await add_user(app.state.ipdl.db, "analyst", Role.ANALYST)
    app.state.ipdl.settings.jobs.max_pending = 1
    try:
        async with client_for(app, "analyst") as analyst:
            assert (
                await analyst.post("/persons", json={"full_name": "Первый Тестовый"})
            ).status_code == 201
            full = await analyst.post("/persons", json={"full_name": "Второй Тестовый"})
            assert full.status_code == 503 and full.json()["error"]["code"] == "queue_full"
            # Без построения портрета карточка создаётся
            assert (
                await analyst.post(
                    "/persons", json={"full_name": "Третий Тестовый", "build": False}
                )
            ).status_code == 201
    finally:
        app.state.ipdl.settings.jobs.max_pending = 50


# ---------------------------------------------------------------- обмен с партнёрами


async def test_partner_exchange(api: tuple[httpx.AsyncClient, Any]) -> None:
    _, app = api
    db: Database = app.state.ipdl.db
    uz = await add_partner(db, "UZ", "ПФР Узбекистана")
    kg = await add_partner(db, "KG", "ПФР Кыргызстана")
    await add_user(db, "analyst", Role.ANALYST)
    await add_user(db, "uzfiu", Role.PARTNER, partner_id=uz)
    await add_user(db, "kgfiu", Role.PARTNER, partner_id=kg)

    async with client_for(app, "analyst") as analyst:
        shared = (
            await analyst.post("/persons", json={"full_name": "Иванов Пётр Сергеевич"})
        ).json()
        secret = (
            await analyst.post("/persons", json={"full_name": "Секретов Секрет", "build": False})
        ).json()
        not_ready = await analyst.post(
            f"/persons/{shared['id']}/requests",
            json={"partner_id": str(uz), "kind": "disclosure", "purpose": "Обмен"},
        )
        assert not_ready.status_code == 409
        portrait_id = await store_done_portrait(db, app, shared["id"])
        disclosure = await analyst.post(
            f"/persons/{shared['id']}/requests",
            json={
                "partner_id": str(uz),
                "kind": "disclosure",
                "purpose": "Ответ на запрос",
                "legal_basis": "Принципы Эгмонт",
            },
        )
        assert disclosure.status_code == 201, disclosure.text
        assert disclosure.json()["status"] == "closed" and disclosure.json()["portrait_id"] == str(
            portrait_id
        )
        info = await analyst.post(
            f"/persons/{shared['id']}/requests",
            json={"partner_id": str(kg), "kind": "info_request", "purpose": "Сведения о счетах"},
        )
        assert info.json()["status"] == "open" and info.json()["direction"] == "outgoing"
        progress = await analyst.patch(
            f"/requests/{info.json()['id']}", json={"status": "in_progress"}
        )
        assert progress.json()["status"] == "in_progress"
        closed = await analyst.patch(
            f"/requests/{info.json()['id']}",
            json={"status": "closed", "response_note": "Получен ответ"},
        )
        assert closed.json()["closed_at"] is not None
        immutable = await analyst.patch(
            f"/requests/{disclosure.json()['id']}", json={"status": "open"}
        )
        assert immutable.status_code == 409

    async with client_for(app, "uzfiu") as partner:
        listed = (await partner.get("/persons")).json()
        assert [p["id"] for p in listed["items"]] == [shared["id"]]
        detail = (await partner.get(f"/persons/{shared['id']}")).json()
        assert detail["can_edit"] is False
        assert [r["partner"]["country"] for r in detail["requests"]] == ["UZ"]
        assert (await partner.get(f"/persons/{secret['id']}")).status_code == 404
        assert (await partner.get(f"/portraits/{portrait_id}/export.pdf")).status_code == 200
        assert (await partner.put(f"/portraits/{portrait_id}/review", json={})).status_code == 403
        asked = await partner.post(
            f"/persons/{shared['id']}/requests",
            json={"partner_id": str(kg), "kind": "info_request", "purpose": "Уточнить связи"},
        )
        assert asked.status_code == 201
        assert (
            asked.json()["direction"] == "incoming" and asked.json()["partner"]["country"] == "UZ"
        )
        forbidden = await partner.post(
            f"/persons/{shared['id']}/requests",
            json={"partner_id": str(uz), "kind": "disclosure", "purpose": "x x x"},
        )
        assert forbidden.status_code == 403
        assert (await partner.get("/partners")).status_code == 403
        assert (await partner.get("/sanctions/lists")).status_code == 403

    async with client_for(app, "kgfiu") as other:
        assert (await other.get("/persons")).json()["total"] == 0
        assert (await other.get(f"/portraits/{portrait_id}")).status_code == 404

    assert "partner_view" in await _audit(db)


# ---------------------------------------------------------------- администрирование и санкции


async def test_admin_and_sanctions(api: tuple[httpx.AsyncClient, Any]) -> None:
    _, app = api
    db: Database = app.state.ipdl.db
    admin_id = await add_user(db, "admin", Role.ADMIN)
    await add_user(db, "analyst", Role.ANALYST)
    from tests.integration.test_sanctions_db import load_fixture_lists

    await load_fixture_lists(db)

    async with client_for(app, "admin") as admin, client_for(app, "analyst") as analyst:
        assert (await analyst.get("/users")).status_code == 403
        partner = await admin.post(
            "/partners", json={"country": "ae", "name": "UAE FIU", "contact": "fiu@example"}
        )
        assert partner.status_code == 201 and partner.json()["country"] == "AE"
        assert (
            await admin.post("/partners", json={"country": "AE", "name": "UAE FIU"})
        ).status_code == 409

        weak = await admin.post(
            "/users",
            json={
                "username": "newbie",
                "display_name": "Новичок",
                "password": "short-1",
                "role": "viewer",
            },
        )
        assert weak.status_code == 422
        no_partner = await admin.post(
            "/users",
            json={
                "username": "fiu",
                "display_name": "FIU",
                "password": "long-enough-pass-1",
                "role": "partner",
            },
        )
        assert no_partner.status_code == 422
        created = await admin.post(
            "/users",
            json={
                "username": "fiu",
                "display_name": "FIU",
                "password": "long-enough-pass-1",
                "role": "partner",
                "partner_id": partner.json()["id"],
            },
        )
        assert created.status_code == 201 and created.json()["partner"]["name"] == "UAE FIU"
        assert (
            await admin.post(
                "/users",
                json={
                    "username": "FIU",
                    "display_name": "Дубль",
                    "password": "long-enough-pass-1",
                    "role": "viewer",
                },
            )
        ).status_code == 409
        disabled = await admin.patch(f"/users/{created.json()['id']}", json={"is_active": False})
        assert disabled.json()["is_active"] is False
        self_lock = await admin.patch(f"/users/{admin_id}", json={"role": "viewer"})
        assert self_lock.status_code == 409

        lists = (await analyst.get("/sanctions/lists")).json()
        assert {x["id"]: x["entries"] for x in lists} == {"eu": 2, "ofac_sdn": 2, "uk": 1, "un": 3}
        found = (
            await analyst.get(
                "/sanctions/search", params={"q": "Виктор Тестман", "birth_date": "1958-05-26"}
            )
        ).json()
        assert {m["list_id"] for m in found["matches"]} == {"ofac_sdn", "eu", "uk"}
        companies = (
            await analyst.get(
                "/sanctions/search", params={"q": "Northwind Trading", "kind": "entity"}
            )
        ).json()
        assert companies["matches"]
        assert (await analyst.post("/sanctions/update")).status_code == 403
        assert (await admin.post("/sanctions/update")).status_code == 202
        assert app.state.ipdl.queue.sanctions_updates == 1

        methodology = (await analyst.get("/methodology")).json()
        assert methodology["risk_model"]["id"].startswith("ipdl-risk")
        assert len(methodology["jurisdictions"]["fatf"]["increased_monitoring"]) == 22

        audit = (await admin.get("/audit", params={"action": "user_created"})).json()
        assert audit["total"] == 1 and audit["items"][0]["username"] == "admin"
        assert (await analyst.get("/audit")).status_code == 403


async def test_health(api: tuple[httpx.AsyncClient, Any]) -> None:
    client, _ = api
    assert (await client.get("/healthz")).json() == {"status": "ok"}
    ready = await client.get("/readyz")
    assert ready.status_code == 200 and ready.json()["checks"] == {"database": True, "queue": True}
    metrics = await client.get("/metrics")
    assert "ipdl_http_request_duration_seconds" in metrics.text
    too_big = await client.post(
        "/api/v1/auth/login", content=b"x" * 300_000, headers={"content-type": "application/json"}
    )
    assert too_big.status_code == 413
