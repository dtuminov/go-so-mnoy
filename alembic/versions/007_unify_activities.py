"""unify events and company_seekings into a single activities entity

Revision ID: 007_unify_activities
Revises: 006_chat_links_and_notify_flags
Create Date: 2026-04-12

Слияние:
    events                     +
    company_seekings              -> activities
    event_participants         +
    company_seeking_responses     -> activity_members
    event_tags                 +
    seeking_tags                  -> activity_tags

`activities.kind` ('event' | 'seeking') различает два типа.
`activities.expires_at` — единое поле «когда исчезает из ленты»:
    - для event:   starts_at + 2 hours (минимальная защита от исчезновения
      события в момент начала; см. tech-debt.md п. 4)
    - для seeking: совпадает с прежним expires_at
`activities.visibility` enum-строка ('open' | 'private') — основа для
approval-flow в следующем коммите.
`activity_members.status` ('pending' | 'joined') — основа для same.

Откат: пересоздаём legacy-таблицы и копируем данные обратно. После downgrade
возвращается ровно тот же набор сущностей, что был до 007 (с возможной
потерей вновь созданных за время жизни 007 activities, у которых не было
аналога в старых сущностях, — но это нормально для отката).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_unify_activities"
down_revision: Union[str, None] = "006_chat_links_and_notify_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── activities ──────────────────────────────────────────────────────────
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "body",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "place_text",
            sa.String(length=512),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("chat_url", sa.String(length=512), nullable=True),
        sa.Column(
            "visibility",
            sa.String(length=16),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "published_notified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "reminder_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # Технические колонки для миграции данных — дропнем после копирования.
        sa.Column("_legacy_kind", sa.String(length=16), nullable=True),
        sa.Column("_legacy_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_activities_city_id"), "activities", ["city_id"], unique=False,
    )
    op.create_index(
        op.f("ix_activities_creator_id"),
        "activities",
        ["creator_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activities_kind"), "activities", ["kind"], unique=False,
    )
    op.create_index(
        op.f("ix_activities_status"), "activities", ["status"], unique=False,
    )
    op.create_index(
        "ix_activities_city_status_starts",
        "activities",
        ["city_id", "status", "starts_at"],
        unique=False,
    )
    op.create_index(
        "ix_activities_city_status_expires",
        "activities",
        ["city_id", "status", "expires_at"],
        unique=False,
    )

    # ── activity_members ────────────────────────────────────────────────────
    op.create_table(
        "activity_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="joined",
        ),
        sa.Column(
            "chat_invite_notified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"], ["activities.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", "user_id", name="uq_activity_member"),
    )
    op.create_index(
        op.f("ix_activity_members_activity_id"),
        "activity_members",
        ["activity_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_activity_members_user_id"),
        "activity_members",
        ["user_id"],
        unique=False,
    )

    # ── activity_tags ───────────────────────────────────────────────────────
    op.create_table(
        "activity_tags",
        sa.Column("activity_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"], ["activities.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("activity_id", "tag_id"),
    )
    op.create_index(
        op.f("ix_activity_tags_tag_id"),
        "activity_tags",
        ["tag_id"],
        unique=False,
    )

    # ── копируем events → activities ────────────────────────────────────────
    op.execute(
        sa.text(
            """
            INSERT INTO activities (
                city_id, creator_id, kind, title, body, starts_at, expires_at,
                place_text, chat_url, visibility, status,
                published_notified, reminder_sent, created_at,
                _legacy_kind, _legacy_id
            )
            SELECT
                city_id, organizer_id, 'event', title, description, starts_at,
                starts_at + interval '2 hours',
                place_text, chat_url, 'open', status,
                published_notified, reminder_sent, created_at,
                'event', id
            FROM events
            """,
        ),
    )

    # ── копируем company_seekings → activities ──────────────────────────────
    op.execute(
        sa.text(
            """
            INSERT INTO activities (
                city_id, creator_id, kind, title, body, starts_at, expires_at,
                place_text, chat_url, visibility, status,
                published_notified, reminder_sent, created_at,
                _legacy_kind, _legacy_id
            )
            SELECT
                city_id, author_id, 'seeking', title, body, NULL, expires_at,
                '', chat_url, 'open', status,
                published_notified, false, created_at,
                'seeking', id
            FROM company_seekings
            """,
        ),
    )

    # ── копируем event_participants → activity_members ──────────────────────
    op.execute(
        sa.text(
            """
            INSERT INTO activity_members (
                activity_id, user_id, status, chat_invite_notified, created_at
            )
            SELECT
                a.id, ep.user_id, 'joined', ep.chat_invite_notified, ep.created_at
            FROM event_participants ep
            JOIN activities a
              ON a._legacy_kind = 'event' AND a._legacy_id = ep.event_id
            """,
        ),
    )

    # ── копируем company_seeking_responses → activity_members ───────────────
    op.execute(
        sa.text(
            """
            INSERT INTO activity_members (
                activity_id, user_id, status, chat_invite_notified, created_at
            )
            SELECT
                a.id, csr.user_id, 'joined', csr.chat_invite_notified, csr.created_at
            FROM company_seeking_responses csr
            JOIN activities a
              ON a._legacy_kind = 'seeking' AND a._legacy_id = csr.seeking_id
            """,
        ),
    )

    # ── копируем event_tags → activity_tags ─────────────────────────────────
    op.execute(
        sa.text(
            """
            INSERT INTO activity_tags (activity_id, tag_id)
            SELECT a.id, et.tag_id
            FROM event_tags et
            JOIN activities a
              ON a._legacy_kind = 'event' AND a._legacy_id = et.event_id
            """,
        ),
    )

    # ── копируем seeking_tags → activity_tags ───────────────────────────────
    op.execute(
        sa.text(
            """
            INSERT INTO activity_tags (activity_id, tag_id)
            SELECT a.id, st.tag_id
            FROM seeking_tags st
            JOIN activities a
              ON a._legacy_kind = 'seeking' AND a._legacy_id = st.seeking_id
            """,
        ),
    )

    # ── удаляем технические колонки ─────────────────────────────────────────
    op.drop_column("activities", "_legacy_id")
    op.drop_column("activities", "_legacy_kind")

    # ── дропаем legacy-таблицы ──────────────────────────────────────────────
    op.drop_table("event_tags")
    op.drop_table("seeking_tags")
    op.drop_table("event_participants")
    op.drop_table("company_seeking_responses")
    op.drop_table("events")
    op.drop_table("company_seekings")


def downgrade() -> None:
    # Воссоздаём legacy-схему ровно так, как она была после миграций 002..006.

    # events
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("place_text", sa.String(length=512), nullable=False, server_default=sa.text("''")),
        sa.Column("chat_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("published_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.ForeignKeyConstraint(["organizer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_city_id"), "events", ["city_id"], unique=False)
    op.create_index(op.f("ix_events_organizer_id"), "events", ["organizer_id"], unique=False)
    op.create_index(op.f("ix_events_status"), "events", ["status"], unique=False)
    op.create_index("ix_events_city_status_starts", "events", ["city_id", "status", "starts_at"], unique=False)

    # company_seekings
    op.create_table(
        "company_seekings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chat_url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("published_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_seekings_author_id"), "company_seekings", ["author_id"], unique=False)
    op.create_index(op.f("ix_company_seekings_city_id"), "company_seekings", ["city_id"], unique=False)
    op.create_index(op.f("ix_company_seekings_status"), "company_seekings", ["status"], unique=False)

    # event_participants
    op.create_table(
        "event_participants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="joined"),
        sa.Column("chat_invite_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_participant"),
    )
    op.create_index(op.f("ix_event_participants_event_id"), "event_participants", ["event_id"], unique=False)
    op.create_index(op.f("ix_event_participants_user_id"), "event_participants", ["user_id"], unique=False)

    # company_seeking_responses
    op.create_table(
        "company_seeking_responses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("seeking_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_invite_notified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["seeking_id"], ["company_seekings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seeking_id", "user_id", name="uq_seeking_response"),
    )
    op.create_index(op.f("ix_company_seeking_responses_seeking_id"), "company_seeking_responses", ["seeking_id"], unique=False)
    op.create_index(op.f("ix_company_seeking_responses_user_id"), "company_seeking_responses", ["user_id"], unique=False)

    # event_tags
    op.create_table(
        "event_tags",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("event_id", "tag_id"),
    )
    op.create_index(op.f("ix_event_tags_tag_id"), "event_tags", ["tag_id"], unique=False)

    # seeking_tags
    op.create_table(
        "seeking_tags",
        sa.Column("seeking_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["seeking_id"], ["company_seekings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("seeking_id", "tag_id"),
    )
    op.create_index(op.f("ix_seeking_tags_tag_id"), "seeking_tags", ["tag_id"], unique=False)

    # Чтобы при upgrade->downgrade связать activity и старые таблицы, мы могли
    # бы хранить _legacy_id, но мы их дропнули. Поэтому restore делаем
    # «лучше, чем ничего»: создаём legacy-строки заново из activities, и id
    # становятся новыми. Это приемлемо для отката тестового окружения; для
    # прод-отката достаточно заархивировать дамп до миграции.

    # events ← activities WHERE kind='event'
    op.execute(
        sa.text(
            """
            INSERT INTO events (
                city_id, organizer_id, title, description, starts_at,
                place_text, chat_url, status,
                published_notified, reminder_sent, created_at
            )
            SELECT
                city_id, creator_id, title, body, starts_at,
                place_text, chat_url, status,
                published_notified, reminder_sent, created_at
            FROM activities
            WHERE kind = 'event' AND starts_at IS NOT NULL
            """,
        ),
    )

    # company_seekings ← activities WHERE kind='seeking'
    op.execute(
        sa.text(
            """
            INSERT INTO company_seekings (
                city_id, author_id, title, body, expires_at, chat_url,
                status, published_notified, created_at
            )
            SELECT
                city_id, creator_id, title, body, expires_at, chat_url,
                status, published_notified, created_at
            FROM activities
            WHERE kind = 'seeking'
            """,
        ),
    )

    # Восстановление участников/тегов после downgrade пропускаем —
    # см. комментарий выше. Если нужен полный откат на проде, восстанавливай
    # из дампа базы, а не из этой downgrade-функции.

    op.drop_index(op.f("ix_activity_tags_tag_id"), table_name="activity_tags")
    op.drop_table("activity_tags")
    op.drop_index(op.f("ix_activity_members_user_id"), table_name="activity_members")
    op.drop_index(op.f("ix_activity_members_activity_id"), table_name="activity_members")
    op.drop_table("activity_members")
    op.drop_index("ix_activities_city_status_expires", table_name="activities")
    op.drop_index("ix_activities_city_status_starts", table_name="activities")
    op.drop_index(op.f("ix_activities_status"), table_name="activities")
    op.drop_index(op.f("ix_activities_kind"), table_name="activities")
    op.drop_index(op.f("ix_activities_creator_id"), table_name="activities")
    op.drop_index(op.f("ix_activities_city_id"), table_name="activities")
    op.drop_table("activities")
