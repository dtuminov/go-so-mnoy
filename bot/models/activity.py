from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.db.base import Base
from bot.models.associations import activity_tags


class Activity(Base):
    """Единая сущность вместо `Event` + `CompanySeeking`.

    Дискриминатор `kind` различает события (`'event'`) и заявки «ищу
    компанию» (`'seeking'`). Семантически:

    - **event**: `starts_at` — когда происходит, `expires_at` —
      `starts_at + продолжительность` (минимум 2 часа), `place_text`
      обязателен в FSM.
    - **seeking**: `starts_at IS NULL`, `expires_at` — до какой даты
      заявка живёт в ленте, `place_text` обычно пустой.

    `visibility` (`'open'` | `'private'`) — поведение «join»: open
    означает мгновенное `joined`, private — заявку с `pending` и
    подтверждением организатором (см. `ActivityMember.status`).
    """

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text(), default="", server_default="")
    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    place_text: Mapped[str] = mapped_column(
        String(512), default="", server_default="",
    )
    chat_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    visibility: Mapped[str] = mapped_column(
        String(16), default="open", server_default="open",
    )
    status: Mapped[str] = mapped_column(
        String(32), index=True, default="draft",
    )
    published_notified: Mapped[bool] = mapped_column(
        default=False, server_default="false",
    )
    reminder_sent: Mapped[bool] = mapped_column(
        default=False, server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    city: Mapped["City"] = relationship(back_populates="activities")
    creator: Mapped["User"] = relationship(
        back_populates="created_activities",
        foreign_keys=[creator_id],
    )
    members: Mapped[list["ActivityMember"]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=activity_tags,
        order_by="Tag.sort_order",
    )

    @property
    def is_event(self) -> bool:
        return self.kind == "event"

    @property
    def is_seeking(self) -> bool:
        return self.kind == "seeking"
