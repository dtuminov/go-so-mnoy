"""notification flags for events, seekings and participants

Revision ID: 004_notification_flags
Revises: 003_user_profile
Create Date: 2026-04-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_notification_flags"
down_revision: Union[str, None] = "003_user_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # отправить автору уведомление когда модератор опубликует
    op.add_column(
        "events",
        sa.Column("published_notified", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "company_seekings",
        sa.Column("published_notified", sa.Boolean(), nullable=False, server_default="false"),
    )
    # напоминание за 2 часа до события всем участникам
    op.add_column(
        "events",
        sa.Column("reminder_sent", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("events", "reminder_sent")
    op.drop_column("company_seekings", "published_notified")
    op.drop_column("events", "published_notified")
