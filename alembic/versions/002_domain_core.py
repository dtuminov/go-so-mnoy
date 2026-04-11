"""cities, events, company seekings, user profile columns

Revision ID: 002_domain_core
Revises: 001_initial_users
Create Date: 2026-04-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_domain_core"
down_revision: Union[str, None] = "001_initial_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.execute(
        sa.text(
            "INSERT INTO cities (name, slug, timezone) "
            "VALUES ('Москва', 'moscow', 'Europe/Moscow')",
        ),
    )

    op.add_column("users", sa.Column("username", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("first_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "place_text",
            sa.String(length=512),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["organizer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_city_id"), "events", ["city_id"], unique=False)
    op.create_index(op.f("ix_events_organizer_id"), "events", ["organizer_id"], unique=False)
    op.create_index(op.f("ix_events_status"), "events", ["status"], unique=False)
    op.create_index(
        "ix_events_city_status_starts",
        "events",
        ["city_id", "status", "starts_at"],
        unique=False,
    )

    op.create_table(
        "event_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="joined",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_participant"),
    )
    op.create_index(
        op.f("ix_event_participants_event_id"),
        "event_participants",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_participants_user_id"),
        "event_participants",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "company_seekings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "body",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_company_seekings_author_id"),
        "company_seekings",
        ["author_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_seekings_city_id"),
        "company_seekings",
        ["city_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_seekings_status"),
        "company_seekings",
        ["status"],
        unique=False,
    )

    op.create_table(
        "company_seeking_responses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("seeking_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seeking_id"], ["company_seekings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seeking_id", "user_id", name="uq_seeking_response"),
    )
    op.create_index(
        op.f("ix_company_seeking_responses_seeking_id"),
        "company_seeking_responses",
        ["seeking_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_company_seeking_responses_user_id"),
        "company_seeking_responses",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_company_seeking_responses_user_id"),
        table_name="company_seeking_responses",
    )
    op.drop_index(
        op.f("ix_company_seeking_responses_seeking_id"),
        table_name="company_seeking_responses",
    )
    op.drop_table("company_seeking_responses")
    op.drop_index(op.f("ix_company_seekings_status"), table_name="company_seekings")
    op.drop_index(op.f("ix_company_seekings_city_id"), table_name="company_seekings")
    op.drop_index(op.f("ix_company_seekings_author_id"), table_name="company_seekings")
    op.drop_table("company_seekings")
    op.drop_index(op.f("ix_event_participants_user_id"), table_name="event_participants")
    op.drop_index(op.f("ix_event_participants_event_id"), table_name="event_participants")
    op.drop_table("event_participants")
    op.drop_index("ix_events_city_status_starts", table_name="events")
    op.drop_index(op.f("ix_events_status"), table_name="events")
    op.drop_index(op.f("ix_events_organizer_id"), table_name="events")
    op.drop_index(op.f("ix_events_city_id"), table_name="events")
    op.drop_table("events")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.drop_column("users", "username")
    op.drop_table("cities")
