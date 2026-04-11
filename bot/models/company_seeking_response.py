from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class CompanySeekingResponse(Base):
    __tablename__ = "company_seeking_responses"
    __table_args__ = (
        UniqueConstraint("seeking_id", "user_id", name="uq_seeking_response"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seeking_id: Mapped[int] = mapped_column(
        ForeignKey("company_seekings.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    chat_invite_notified: Mapped[bool] = mapped_column(
        Boolean(),
        default=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    seeking: Mapped["CompanySeeking"] = relationship(back_populates="responses")
    user: Mapped["User"] = relationship(back_populates="company_seeking_responses")
