from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
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

    organized_events: Mapped[list["Event"]] = relationship(back_populates="organizer")
    event_participations: Mapped[list["EventParticipant"]] = relationship(
        back_populates="user",
    )
    company_seekings: Mapped[list["CompanySeeking"]] = relationship(back_populates="author")
    company_seeking_responses: Mapped[list["CompanySeekingResponse"]] = relationship(
        back_populates="user",
    )
