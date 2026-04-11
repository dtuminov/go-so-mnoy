"""user profile for event join (avatar, age, bio)

Revision ID: 003_user_profile
Revises: 002_domain_core
Create Date: 2026-04-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_user_profile"
down_revision: Union[str, None] = "002_domain_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("avatar_file_id", sa.String(length=512), nullable=True),
    )
    op.add_column("users", sa.Column("age", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "bio")
    op.drop_column("users", "age")
    op.drop_column("users", "avatar_file_id")
