from __future__ import annotations

from datetime import datetime

from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger(), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
    avatar_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # {"event_tag_ids": [int, ...], "seeking_tag_ids": [int, ...]}
    search_prefs: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_activities: Mapped[list["Activity"]] = relationship(
        back_populates="creator",
    )
    activity_memberships: Mapped[list["ActivityMember"]] = relationship(
        back_populates="user",
    )
