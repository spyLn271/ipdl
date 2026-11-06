"""Начальная схема: пользователи, реестр, портреты, журнал обращений, санкции

Revision ID: 0e9505e50d14
Revises:
Create Date: 2026-10-27 20:54:37.523929+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0e9505e50d14"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Нечёткий поиск по реестру и санкционным спискам
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "partners",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("contact", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partners")),
        sa.UniqueConstraint("country", "name", name="uq_partners_country_name"),
    )
    op.create_table(
        "sanctions_lists",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("entries", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="never", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sanctions_lists")),
    )
    op.create_table(
        "sanctions_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("list_id", sa.String(length=32), nullable=False),
        sa.Column("ref", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("primary_name", sa.Text(), nullable=False),
        sa.Column("birth_dates", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("nationalities", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("programs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("listed_on", sa.String(length=10), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["sanctions_lists.id"],
            name=op.f("fk_sanctions_entries_list_id_sanctions_lists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sanctions_entries")),
    )
    op.create_index(
        op.f("ix_sanctions_entries_list_id"), "sanctions_entries", ["list_id"], unique=False
    )
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "admin",
                "analyst",
                "viewer",
                "partner",
                name="user_role",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("partner_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("failed_logins", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_users_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=True),
        sa.Column("object_id", sa.String(length=64), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_events_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index("ix_audit_events_at", "audit_events", ["at"], unique=False)
    op.create_index(
        "ix_audit_events_object", "audit_events", ["object_type", "object_id"], unique=False
    )
    op.create_table(
        "persons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("latin_name", sa.String(length=200), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("citizenship", sa.String(length=2), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("pep_category", sa.String(length=32), nullable=True),
        sa.Column("pep_tenure", sa.String(length=16), nullable=True),
        sa.Column("position", sa.Text(), nullable=True),
        sa.Column("organization", sa.Text(), nullable=True),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=True),
        sa.Column("current_portrait_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_persons_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_persons")),
    )
    op.create_index(
        "ix_persons_search_text_trgm",
        "persons",
        ["search_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.create_index("ix_persons_updated_at", "persons", ["updated_at"], unique=False)
    op.create_table(
        "sanctions_names",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("folded", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["sanctions_entries.id"],
            name=op.f("fk_sanctions_names_entry_id_sanctions_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sanctions_names")),
    )
    op.create_index(
        op.f("ix_sanctions_names_entry_id"), "sanctions_names", ["entry_id"], unique=False
    )
    op.create_index(
        "ix_sanctions_names_folded_trgm",
        "sanctions_names",
        ["folded"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"folded": "gin_trgm_ops"},
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    op.create_table(
        "portraits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "done",
                "failed",
                name="job_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("review", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_portraits_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["persons.id"],
            name=op.f("fk_portraits_person_id_persons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portraits")),
        sa.UniqueConstraint("person_id", "version", name="uq_portraits_person_version"),
    )
    op.create_index("ix_portraits_status", "portraits", ["status"], unique=False)
    # persons ↔ portraits ссылаются друг на друга — внешний ключ после создания обеих таблиц
    op.create_foreign_key(
        op.f("fk_persons_current_portrait_id_portraits"),
        "persons",
        "portraits",
        ["current_portrait_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("partner_id", sa.UUID(), nullable=False),
        sa.Column("portrait_id", sa.UUID(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum(
                "incoming",
                "outgoing",
                name="request_direction",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.Enum(
                "info_request",
                "disclosure",
                name="request_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "in_progress",
                "closed",
                name="request_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("legal_basis", sa.Text(), nullable=True),
        sa.Column("response_note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_requests_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["partner_id"],
            ["partners.id"],
            name=op.f("fk_requests_partner_id_partners"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["persons.id"],
            name=op.f("fk_requests_person_id_persons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portrait_id"],
            ["portraits.id"],
            name=op.f("fk_requests_portrait_id_portraits"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requests")),
    )
    op.create_index("ix_requests_partner_kind", "requests", ["partner_id", "kind"], unique=False)
    op.create_index("ix_requests_person_id", "requests", ["person_id"], unique=False)


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_persons_current_portrait_id_portraits"), "persons", type_="foreignkey"
    )
    op.drop_index("ix_requests_person_id", table_name="requests")
    op.drop_index("ix_requests_partner_kind", table_name="requests")
    op.drop_table("requests")
    op.drop_index("ix_portraits_status", table_name="portraits")
    op.drop_table("portraits")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index(
        "ix_sanctions_names_folded_trgm",
        table_name="sanctions_names",
        postgresql_using="gin",
        postgresql_ops={"folded": "gin_trgm_ops"},
    )
    op.drop_index(op.f("ix_sanctions_names_entry_id"), table_name="sanctions_names")
    op.drop_table("sanctions_names")
    op.drop_index("ix_persons_updated_at", table_name="persons")
    op.drop_index(
        "ix_persons_search_text_trgm",
        table_name="persons",
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )
    op.drop_table("persons")
    op.drop_index("ix_audit_events_object", table_name="audit_events")
    op.drop_index("ix_audit_events_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_index(op.f("ix_sanctions_entries_list_id"), table_name="sanctions_entries")
    op.drop_table("sanctions_entries")
    op.drop_table("sanctions_lists")
    op.drop_table("partners")
