"""add moderation_notified flag to activities

Revision ID: 009_moderation_notified
Revises: 008_activity_cover
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_moderation_notified"
down_revision: Union[str, None] = "008_activity_cover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column(
            "moderation_notified",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
    # Новые записи будут false, старые уже промодерированы — true.


def downgrade() -> None:
    op.drop_column("activities", "moderation_notified")
