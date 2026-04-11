"""activity cover photo

Revision ID: 008_activity_cover
Revises: 007_unify_activities
Create Date: 2026-04-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_activity_cover"
down_revision: Union[str, None] = "007_unify_activities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("cover_file_id", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("activities", "cover_file_id")
