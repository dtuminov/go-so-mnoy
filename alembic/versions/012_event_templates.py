"""Event templates for channel deep links

Revision ID: 012_event_templates
Revises: 011_more_cities
Create Date: 2026-04-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_event_templates"
down_revision: Union[str, None] = "011_more_cities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("place_text", sa.String(512), server_default="", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_file_id", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column(
        "activities",
        sa.Column("template_id", sa.Integer(), nullable=True),
    )
    op.create_index(op.f("ix_activities_template_id"), "activities", ["template_id"])
    op.create_foreign_key(
        "fk_activities_template_id",
        "activities",
        "event_templates",
        ["template_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_activities_template_id", "activities", type_="foreignkey")
    op.drop_index(op.f("ix_activities_template_id"), table_name="activities")
    op.drop_column("activities", "template_id")
    op.drop_table("event_templates")
