from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base
from bot.models.associations import seeking_tags


class CompanySeeking(Base):
    __tablename__ = "company_seekings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text(), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    chat_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")
    published_notified: Mapped[bool] = mapped_column(default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    city: Mapped["City"] = relationship(back_populates="company_seekings")
    author: Mapped["User"] = relationship(
        back_populates="company_seekings",
        foreign_keys=[author_id],
    )
    responses: Mapped[list["CompanySeekingResponse"]] = relationship(
        back_populates="seeking",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=seeking_tags,
        order_by="Tag.sort_order",
    )
