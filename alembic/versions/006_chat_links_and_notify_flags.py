"""chat_url on events/seekings and chat_invite_notified on participants/responses

Revision ID: 006_chat_links_and_notify_flags
Revises: 005_tags_and_search_prefs
Create Date: 2026-04-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_chat_links_and_notify_flags"
down_revision: Union[str, None] = "005_tags_and_search_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column("chat_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "company_seekings",
        sa.Column("chat_url", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "event_participants",
        sa.Column(
            "chat_invite_notified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "company_seeking_responses",
        sa.Column(
            "chat_invite_notified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("company_seeking_responses", "chat_invite_notified")
    op.drop_column("event_participants", "chat_invite_notified")
    op.drop_column("company_seekings", "chat_url")
    op.drop_column("events", "chat_url")
