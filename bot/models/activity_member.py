from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base


class ActivityMember(Base):
    """Запись о вступлении пользователя в `Activity`.

    Заменяет `EventParticipant` + `CompanySeekingResponse`.

    `status`:
    - `'joined'`  — подтверждённое участие (для open сразу, для private
      — после approve организатора).
    - `'pending'` — ожидание подтверждения организатором (только для
      `Activity.visibility == 'private'`).
    """

    __tablename__ = "activity_members"
    __table_args__ = (
        UniqueConstraint("activity_id", "user_id", name="uq_activity_member"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    status: Mapped[str] = mapped_column(String(32), default="joined")
    chat_invite_notified: Mapped[bool] = mapped_column(
        default=False, server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    activity: Mapped["Activity"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="activity_memberships")
