"""tags taxonomy, event/seeking tag links, users.search_prefs

Revision ID: 005_tags_and_search_prefs
Revises: 004_notification_flags
Create Date: 2026-04-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_tags_and_search_prefs"
down_revision: Union[str, None] = "004_notification_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Стартовый фиксированный набор тегов. Правится только новой миграцией.
INITIAL_TAGS: list[tuple[str, str, str, int]] = [
    # (slug, name, emoji, sort_order)
    ("bars", "Бары", "🍺", 10),
    ("board_games", "Настолки", "🎲", 20),
    ("cinema", "Кино", "🎬", 30),
    ("exhibitions", "Выставки", "🎨", 40),
    ("concerts", "Концерты", "🎤", 50),
    ("sport", "Спорт", "🏃", 60),
    ("walk", "Прогулка", "🚶", 70),
    ("food", "Еда", "🍽", 80),
    ("talk", "Поговорить", "💬", 90),
    ("other", "Другое", "🧩", 100),
]


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("emoji", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "event_tags",
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("event_id", "tag_id"),
    )
    op.create_index(
        op.f("ix_event_tags_tag_id"),
        "event_tags",
        ["tag_id"],
        unique=False,
    )

    op.create_table(
        "seeking_tags",
        sa.Column("seeking_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["seeking_id"], ["company_seekings.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("seeking_id", "tag_id"),
    )
    op.create_index(
        op.f("ix_seeking_tags_tag_id"),
        "seeking_tags",
        ["tag_id"],
        unique=False,
    )

    op.add_column(
        "users",
        sa.Column(
            "search_prefs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # Сид стартового набора тегов. ON CONFLICT DO NOTHING — повторный прогон безопасен.
    tags_table = sa.table(
        "tags",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("emoji", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    for slug, name, emoji, order in INITIAL_TAGS:
        op.execute(
            sa.text(
                "INSERT INTO tags (slug, name, emoji, sort_order, is_active) "
                "VALUES (:slug, :name, :emoji, :sort_order, true) "
                "ON CONFLICT (slug) DO NOTHING"
            ).bindparams(slug=slug, name=name, emoji=emoji, sort_order=order)
        )


def downgrade() -> None:
    op.drop_column("users", "search_prefs")
    op.drop_index(op.f("ix_seeking_tags_tag_id"), table_name="seeking_tags")
    op.drop_table("seeking_tags")
    op.drop_index(op.f("ix_event_tags_tag_id"), table_name="event_tags")
    op.drop_table("event_tags")
    op.drop_table("tags")
