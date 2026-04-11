"""Сервисный слой для единой сущности `Activity` (события + заявки)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.constants import (
    ACTIVITY_CANCELLED,
    ACTIVITY_CLOSED,
    ACTIVITY_EVENT,
    ACTIVITY_PENDING_REVIEW,
    ACTIVITY_PUBLISHED,
    ACTIVITY_SEEKING,
    MEMBER_JOINED,
    MEMBER_PENDING,
    MOSCOW_CITY_ID,
    VISIBILITY_OPEN,
    VISIBILITY_PRIVATE,
)
from bot.models import Activity, ActivityMember, Tag, User, activity_tags

# Длительность события по умолчанию, если организатор не указал явно.
# Сейчас FSM не спрашивает — берём фикс. См. tech-debt.md, п. 4.
DEFAULT_EVENT_DURATION = timedelta(hours=2)


# ──────────────────────────── чтение ────────────────────────────────────────


async def list_published_activities(
    session: AsyncSession,
    *,
    kind: str,
    city_id: int = MOSCOW_CITY_ID,
    tag_ids: list[int] | None = None,
    limit: int = 100,
) -> list[Activity]:
    """Лента опубликованных активностей.

    `kind`:
        - `'event'`   — отсортировано по `starts_at` ASC, фильтр
          `expires_at >= now()` (т.е. событие не истекло).
        - `'seeking'` — отсортировано по `created_at` DESC, фильтр
          `expires_at >= now()`.

    Если `tag_ids` непустой — оставляем активности, у которых есть
    хотя бы один из выбранных тегов (OR-семантика).
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(Activity)
        .where(Activity.city_id == city_id)
        .where(Activity.kind == kind)
        .where(Activity.status == ACTIVITY_PUBLISHED)
        .where(Activity.expires_at >= now)
        .options(selectinload(Activity.tags))
        .limit(limit)
    )
    if kind == ACTIVITY_EVENT:
        stmt = stmt.order_by(Activity.starts_at.asc())
    else:
        stmt = stmt.order_by(Activity.created_at.desc())

    if tag_ids:
        subq = (
            select(activity_tags.c.activity_id)
            .where(activity_tags.c.activity_id == Activity.id)
            .where(activity_tags.c.tag_id.in_(tag_ids))
        )
        stmt = stmt.where(subq.exists())

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_activity(session: AsyncSession, activity_id: int) -> Activity | None:
    stmt = (
        select(Activity)
        .where(Activity.id == activity_id)
        .options(selectinload(Activity.tags))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_creator_summary(
    session: AsyncSession,
    activity: Activity,
) -> tuple[str | None, int | None]:
    """Возвращает `(name, age)` создателя — то, что нужно карточке заявки.
    Используется только для seeking, чтобы показать «лицо» автора."""
    user = await session.get(User, activity.creator_id)
    if user is None:
        return None, None
    name = user.first_name or user.username
    return name, user.age


async def count_joined_members(session: AsyncSession, activity_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(ActivityMember)
        .where(ActivityMember.activity_id == activity_id)
        .where(ActivityMember.status == MEMBER_JOINED)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def count_pending_members(session: AsyncSession, activity_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(ActivityMember)
        .where(ActivityMember.activity_id == activity_id)
        .where(ActivityMember.status == MEMBER_PENDING)
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def get_activity_members(
    session: AsyncSession,
    *,
    activity_id: int,
    status: str | None = None,
) -> list[tuple[ActivityMember, User]]:
    stmt = (
        select(ActivityMember, User)
        .join(User, User.id == ActivityMember.user_id)
        .where(ActivityMember.activity_id == activity_id)
        .order_by(ActivityMember.created_at.asc())
    )
    if status is not None:
        stmt = stmt.where(ActivityMember.status == status)
    result = await session.execute(stmt)
    return list(result.all())


# ──────────────────────────── членство пользователя ─────────────────────────


async def get_user_membership(
    session: AsyncSession,
    *,
    activity_id: int,
    user_id: int,
) -> ActivityMember | None:
    result = await session.execute(
        select(ActivityMember)
        .where(ActivityMember.activity_id == activity_id)
        .where(ActivityMember.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def join_activity(
    session: AsyncSession,
    *,
    activity: Activity,
    user_id: int,
) -> tuple[ActivityMember | None, str]:
    """Создаёт запись участника. Возвращает `(member, action)`, где
    `action`:

    - `'created_joined'` — создана новая запись со статусом `joined`
      (для open-активностей);
    - `'created_pending'` — создана новая запись со статусом `pending`
      (для private-активностей);
    - `'already'` — запись уже существует, ничего не меняем.
    """
    existing = await get_user_membership(
        session, activity_id=activity.id, user_id=user_id,
    )
    if existing is not None:
        return existing, "already"

    if activity.visibility == VISIBILITY_PRIVATE:
        new_status = MEMBER_PENDING
        action = "created_pending"
    else:
        new_status = MEMBER_JOINED
        action = "created_joined"

    member = ActivityMember(
        activity_id=activity.id,
        user_id=user_id,
        status=new_status,
    )
    session.add(member)
    await session.flush()
    return member, action


async def leave_activity(
    session: AsyncSession,
    *,
    activity_id: int,
    user_id: int,
) -> bool:
    """Удаляет запись участника независимо от status. Возвращает True,
    если запись была."""
    result = await session.execute(
        select(ActivityMember.id).where(
            ActivityMember.activity_id == activity_id,
            ActivityMember.user_id == user_id,
        )
    )
    if result.first() is None:
        return False
    await session.execute(
        delete(ActivityMember).where(
            ActivityMember.activity_id == activity_id,
            ActivityMember.user_id == user_id,
        )
    )
    return True


async def approve_member(
    session: AsyncSession,
    *,
    activity_id: int,
    user_id: int,
) -> bool:
    """Переводит pending → joined. False, если записи не было или статус
    не pending."""
    result = await session.execute(
        select(ActivityMember.id, ActivityMember.status).where(
            ActivityMember.activity_id == activity_id,
            ActivityMember.user_id == user_id,
        )
    )
    row = result.first()
    if row is None or row.status != MEMBER_PENDING:
        return False
    await session.execute(
        update(ActivityMember)
        .where(ActivityMember.activity_id == activity_id)
        .where(ActivityMember.user_id == user_id)
        .values(status=MEMBER_JOINED)
    )
    return True


async def reject_member(
    session: AsyncSession,
    *,
    activity_id: int,
    user_id: int,
) -> bool:
    """Отказ — удаление записи (по решению: можно подавать заявки повторно)."""
    return await leave_activity(
        session, activity_id=activity_id, user_id=user_id,
    )


async def is_user_joined(
    session: AsyncSession,
    *,
    activity_id: int,
    user_id: int,
) -> bool:
    """Только подтверждённое участие (для отображения кнопки чата и т.п.)."""
    result = await session.execute(
        select(ActivityMember.id)
        .where(ActivityMember.activity_id == activity_id)
        .where(ActivityMember.user_id == user_id)
        .where(ActivityMember.status == MEMBER_JOINED)
    )
    return result.first() is not None


# ──────────────────────────── списки для профиля ────────────────────────────


async def get_user_joined_activities(
    session: AsyncSession,
    *,
    user_id: int,
    kind: str,
    limit: int = 10,
) -> list[Activity]:
    """Активности, в которых пользователь — joined-член. Для events
    отсекаем уже истёкшие; для seekings — закрытые."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(Activity)
        .join(ActivityMember, ActivityMember.activity_id == Activity.id)
        .where(ActivityMember.user_id == user_id)
        .where(ActivityMember.status == MEMBER_JOINED)
        .where(Activity.kind == kind)
        .where(Activity.status == ACTIVITY_PUBLISHED)
        .where(Activity.expires_at >= now)
        .options(selectinload(Activity.tags))
        .limit(limit)
    )
    if kind == ACTIVITY_EVENT:
        stmt = stmt.order_by(Activity.starts_at.asc())
    else:
        stmt = stmt.order_by(Activity.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_pending_activities(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 10,
) -> list[Activity]:
    """Заявки на вступление, ожидающие подтверждения организатором
    (исходящие: Я жду, когда кто-то меня подтвердит)."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(Activity)
        .join(ActivityMember, ActivityMember.activity_id == Activity.id)
        .where(ActivityMember.user_id == user_id)
        .where(ActivityMember.status == MEMBER_PENDING)
        .where(Activity.status == ACTIVITY_PUBLISHED)
        .where(Activity.expires_at >= now)
        .options(selectinload(Activity.tags))
        .order_by(Activity.expires_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_activities_with_incoming_pending(
    session: AsyncSession,
    *,
    creator_id: int,
    limit: int = 20,
) -> list[Activity]:
    """Мои активности, у которых есть хотя бы один pending-член
    (входящие: кто-то ждёт моего решения). Только для private."""
    now = datetime.now(timezone.utc)
    inner = (
        select(ActivityMember.activity_id)
        .where(ActivityMember.status == MEMBER_PENDING)
    )
    stmt = (
        select(Activity)
        .where(Activity.creator_id == creator_id)
        .where(Activity.status == ACTIVITY_PUBLISHED)
        .where(Activity.expires_at >= now)
        .where(Activity.id.in_(inner))
        .options(selectinload(Activity.tags))
        .order_by(Activity.expires_at.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_role_in_activity(
    session: AsyncSession,
    *,
    activity: Activity,
    user_id: int,
) -> str:
    """Возвращает одно из: `'creator'`, `'joined'`, `'pending'`, `'none'`.
    Используется экраном деталей активности в профиле, чтобы выбрать
    правильный набор управляющих кнопок."""
    if activity.creator_id == user_id:
        return "creator"
    membership = await get_user_membership(
        session, activity_id=activity.id, user_id=user_id,
    )
    if membership is None:
        return "none"
    return membership.status  # 'joined' | 'pending'


async def get_user_created_activities(
    session: AsyncSession,
    *,
    user_id: int,
    kind: str,
    limit: int = 10,
) -> list[Activity]:
    """Активности, которые создал этот пользователь (живые)."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(Activity)
        .where(Activity.creator_id == user_id)
        .where(Activity.kind == kind)
        .where(Activity.expires_at >= now)
        .where(
            Activity.status.in_([ACTIVITY_PENDING_REVIEW, ACTIVITY_PUBLISHED]),
        )
        .options(selectinload(Activity.tags))
        .limit(limit)
    )
    if kind == ACTIVITY_EVENT:
        stmt = stmt.order_by(Activity.starts_at.asc())
    else:
        stmt = stmt.order_by(Activity.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ──────────────────────────── модерация / lifecycle ─────────────────────────


async def cancel_activity(
    session: AsyncSession,
    *,
    activity_id: int,
    actor_id: int,
) -> bool:
    """Отменяет событие. Только creator. Возвращает True при успехе."""
    result = await session.execute(
        select(Activity.id, Activity.kind).where(
            Activity.id == activity_id,
            Activity.creator_id == actor_id,
        )
    )
    if result.first() is None:
        return False
    await session.execute(
        update(Activity)
        .where(Activity.id == activity_id)
        .values(status=ACTIVITY_CANCELLED),
    )
    return True


async def close_activity(
    session: AsyncSession,
    *,
    activity_id: int,
    actor_id: int,
) -> bool:
    """Закрывает заявку. Только creator."""
    result = await session.execute(
        select(Activity.id).where(
            Activity.id == activity_id,
            Activity.creator_id == actor_id,
        )
    )
    if result.first() is None:
        return False
    await session.execute(
        update(Activity)
        .where(Activity.id == activity_id)
        .values(status=ACTIVITY_CLOSED),
    )
    return True


# ──────────────────────────── создание / правка ─────────────────────────────


async def create_event_draft(
    session: AsyncSession,
    *,
    creator_id: int,
    city_id: int,
    title: str,
    description: str,
    starts_at: datetime,
    place_text: str,
    chat_url: str | None = None,
    visibility: str = VISIBILITY_OPEN,
    tag_ids: list[int] | None = None,
    duration: timedelta = DEFAULT_EVENT_DURATION,
) -> Activity:
    activity = Activity(
        city_id=city_id,
        creator_id=creator_id,
        kind=ACTIVITY_EVENT,
        title=title,
        body=description,
        starts_at=starts_at,
        expires_at=starts_at + duration,
        place_text=place_text,
        chat_url=chat_url,
        visibility=visibility,
        status=ACTIVITY_PENDING_REVIEW,
    )
    session.add(activity)
    await session.flush()
    if tag_ids:
        await session.execute(
            activity_tags.insert().values(
                [{"activity_id": activity.id, "tag_id": tid} for tid in tag_ids]
            )
        )
    return activity


async def create_seeking_draft(
    session: AsyncSession,
    *,
    creator_id: int,
    city_id: int,
    title: str,
    body: str,
    expires_at: datetime,
    chat_url: str | None = None,
    visibility: str = VISIBILITY_OPEN,
    tag_ids: list[int] | None = None,
) -> Activity:
    activity = Activity(
        city_id=city_id,
        creator_id=creator_id,
        kind=ACTIVITY_SEEKING,
        title=title,
        body=body,
        starts_at=None,
        expires_at=expires_at,
        place_text="",
        chat_url=chat_url,
        visibility=visibility,
        status=ACTIVITY_PENDING_REVIEW,
    )
    session.add(activity)
    await session.flush()
    if tag_ids:
        await session.execute(
            activity_tags.insert().values(
                [{"activity_id": activity.id, "tag_id": tid} for tid in tag_ids]
            )
        )
    return activity


async def update_chat_url(
    session: AsyncSession,
    *,
    activity_id: int,
    actor_id: int,
    new_url: str | None,
) -> tuple[bool, str | None, str | None]:
    """Симметрия с прежним `update_event_chat_url`. Возвращает
    `(ok, old_url, new_url)`."""
    row = await session.execute(
        select(Activity.chat_url)
        .where(Activity.id == activity_id)
        .where(Activity.creator_id == actor_id),
    )
    current = row.first()
    if current is None:
        return False, None, None
    old_url = current[0]
    await session.execute(
        update(Activity).where(Activity.id == activity_id).values(chat_url=new_url),
    )
    return True, old_url, new_url


async def update_visibility(
    session: AsyncSession,
    *,
    activity_id: int,
    actor_id: int,
    new_visibility: str,
) -> bool:
    """Меняет visibility. Только creator. Возвращает True при успехе."""
    if new_visibility not in (VISIBILITY_OPEN, VISIBILITY_PRIVATE):
        return False
    row = await session.execute(
        select(Activity.id)
        .where(Activity.id == activity_id)
        .where(Activity.creator_id == actor_id),
    )
    if row.first() is None:
        return False
    await session.execute(
        update(Activity)
        .where(Activity.id == activity_id)
        .values(visibility=new_visibility),
    )
    return True
