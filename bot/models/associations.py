"""Ассоциативные таблицы для many-to-many связей."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, Table

from bot.db.base import Base


event_tags = Table(
    "event_tags",
    Base.metadata,
    Column(
        "event_id",
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
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


seeking_tags = Table(
    "seeking_tags",
    Base.metadata,
    Column(
        "seeking_id",
        Integer,
        ForeignKey("company_seekings.id", ondelete="CASCADE"),
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
