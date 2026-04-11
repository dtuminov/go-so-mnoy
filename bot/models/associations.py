"""Ассоциативные таблицы для many-to-many связей."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, Table

from bot.db.base import Base


activity_tags = Table(
    "activity_tags",
    Base.metadata,
    Column(
        "activity_id",
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)
