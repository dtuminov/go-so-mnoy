"""Хэндлеры действий над `Activity`: лента/открытие/join/leave/members/
cancel/close + approval flow для private активностей."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import (
    ACTIVITY_EVENT,
    ACTIVITY_PUBLISHED,
    ACTIVITY_SEEKING,
    MEMBER_JOINED,
    MEMBER_PENDING,
    VISIBILITY_PRIVATE,
)
from bot.handlers.profile import ProfileSG, begin_profile_flow
from bot.keyboards.activity_feed import format_activity_card_text
from bot.models import Activity, ActivityMember
from bot.services.activities import (
    approve_member,
    cancel_activity,
    close_activity,
    count_joined_members,
    get_activity,
    get_activity_members,
    get_creator_summary,
    get_user_membership,
    is_user_joined,
    join_activity,
    leave_activity,
    list_published_activities,
    reject_member,
)
from bot.services.activity_feed import build_activity_feed_view
from bot.services.chat_invite_notify import mark_member_notified
from bot.services.cover import edit_to_activity_cover, send_activity_cover
from bot.services.member_carousel import (
    CarouselContext,
    build_member_carousel_view,
)
from bot.services.notifications import (
    notify_creator_about_new_member,
    notify_members_about_cancel,
    notify_user_about_decision,
)
from bot.services.profile_view import rerender_profile_to_hub
from bot.services.search_prefs import (
    get_event_tag_filter,
    get_filter_city_id,
    get_seeking_tag_filter,
)
from bot.services.users import (
    get_user_by_id,
    is_profile_complete,
    upsert_telegram_user,
)
from bot.utils.formatting import esc

router = Router(name="activity")


# ──────────────────────────── helpers ────────────────────────────────────────


def _effective_city_id(user) -> int:
    """Возвращает city_id для фильтра (из search_prefs или профиля)."""
    filter_city_id = get_filter_city_id(user)
    return filter_city_id if filter_city_id is not None else user.city_id


async def _effective_city_name(session, user) -> str:
    """Возвращает имя города для ленты."""
    from bot.models import City
    city = await session.get(City, _effective_city_id(user))
    return city.name if city else ""


def _tag_filter(user, kind: str) -> list[int]:
    if kind == ACTIVITY_EVENT:
        return get_event_tag_filter(user)
    return get_seeking_tag_filter(user)


def _no_members_alert_text(kind: str) -> str:
    return (
        "Пока никто не записался."
        if kind == ACTIVITY_EVENT
        else "Пока нет откликов."
    )


def _members_header(kind: str, title: str) -> str:
    if kind == ACTIVITY_EVENT:
        return f"<b>Участники «{esc(title)}»:</b>"
    return f"<b>Отклики на «{esc(title)}»:</b>"


def _is_profile_context(callback: CallbackQuery) -> bool:
    """Дискриминатор «откуда нажата кнопка» по inline-клавиатуре
    исходного сообщения. Профиль использует callback'и `prf:*`,
    лента — `af:*` / `tp:*` / etc. Если в текущей клавиатуре есть
    хотя бы одна `prf:*` кнопка — это профильное сообщение.

    После того как лента стала photo-сообщением, проверка
    `callback.message.photo` уже не различает контексты — оба photo.
    """
    msg = callback.message
    if msg is None or msg.reply_markup is None:
        return False
    for row in msg.reply_markup.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("prf:"):
                return True
    return False


async def _render_card_text(session: AsyncSession, activity: Activity) -> str:
    """Готовит текст карточки активности с учётом kind: для seeking
    подгружает имя автора, чтобы карточка не теряла «лицо» автора при
    ручной перерисовке."""
    members_count = await count_joined_members(session, activity.id)
    author_name = author_age = None
    if activity.kind == ACTIVITY_SEEKING:
        author_name, author_age = await get_creator_summary(session, activity)
    return format_activity_card_text(
        activity,
        members=members_count,
        author_name=author_name,
        author_age=author_age,
    )


async def _rerender_feed_card(
    callback: CallbackQuery,
    session: AsyncSession,
    *,
    user,
    activity: Activity,
) -> None:
    """Полная перерисовка карточки активности в ленте после join/leave
    того же юзера. Сохраняет ряд навигации, кнопку фильтров и кнопку
    чата — переиспользует тот же `build_activity_feed_view`, что
    рисует ленту изначально.

    Индекс активности в текущем (отфильтрованном) списке ищем линейным
    сканом — список ограничен `limit=100`, это дёшево.

    Карточка ленты — это photo-сообщение, поэтому используем
    `edit_to_activity_cover` (`edit_message_media`) — она же сама
    глотает «message is not modified».
    """
    if callback.message is None:
        return
    tag_ids = _tag_filter(user, activity.kind) or None
    city_name = await _effective_city_name(session, user)
    activities = await list_published_activities(
        session, kind=activity.kind, city_id=_effective_city_id(user), tag_ids=tag_ids,
    )
    idx = next(
        (i for i, a in enumerate(activities) if a.id == activity.id),
        0,
    )
    view = await build_activity_feed_view(
        session,
        kind=activity.kind,
        index=idx,
        city_id=_effective_city_id(user),
        city_name=city_name,
        tag_ids=tag_ids,
        viewer_user_id=user.id,
    )
    if view is None:
        return
    cover_file_id, text, kb = view
    await edit_to_activity_cover(
        callback.message,
        cover_file_id=cover_file_id,
        caption=text,
        reply_markup=kb,
    )


# ──────────────────────────── лента: пагинация ───────────────────────────────


@router.callback_query(F.data.startswith("af:g:"))
async def on_feed_page(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        _, _, kind, idx_raw = callback.data.split(":", 3)
        idx = int(idx_raw)
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    city_name = await _effective_city_name(session, user)
    view = await build_activity_feed_view(
        session,
        kind=kind,
        index=idx,
        city_id=_effective_city_id(user),
        city_name=city_name,
        tag_ids=_tag_filter(user, kind) or None,
        viewer_user_id=user.id,
    )
    if view is None:
        await callback.answer("Больше нет", show_alert=True)
        return
    cover_file_id, text, kb = view
    await edit_to_activity_cover(
        callback.message,
        cover_file_id=cover_file_id,
        caption=text,
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("af:c:"))
async def on_feed_counter(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        _, _, kind, idx_raw = callback.data.split(":", 3)
        idx = int(idx_raw)
    except (IndexError, ValueError):
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    city_name = await _effective_city_name(session, user)
    view = await build_activity_feed_view(
        session,
        kind=kind,
        index=idx,
        city_id=_effective_city_id(user),
        city_name=city_name,
        tag_ids=_tag_filter(user, kind) or None,
        viewer_user_id=user.id,
    )
    if view is None:
        await callback.answer()
        return
    # `view` уже посчитан с правильным total в клавиатуре; counter сам по
    # себе ничего не делает кроме показа alert'а — берём текст у клавиатуры.
    # Простоты ради — просто отдаём пустой ack: индексы видны в кнопке.
    await callback.answer()


# ──────────────────────────── join (универсальный) ───────────────────────────


@router.callback_query(F.data.startswith("aj:"))
async def on_join(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    activity = await get_activity(session, activity_id)
    if activity is None or activity.status != ACTIVITY_PUBLISHED:
        await callback.answer("Уже недоступно", show_alert=True)
        return

    # Если идёт анкета — запоминаем target и продолжим после.
    current = await state.get_state()
    if current is not None and current.startswith(ProfileSG.__name__):
        await state.update_data({"pending_join_activity_id": activity_id})
        await callback.answer("Ок — после анкеты подадим заявку.", show_alert=False)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    if not is_profile_complete(user):
        await begin_profile_flow(
            callback.message,
            state,
            pending_event_id=None,
            pending_seeking_id=None,
        )
        await state.update_data({"pending_join_activity_id": activity_id})
        await callback.answer("Сначала анкета 👇")
        return

    if user.id == activity.creator_id:
        if activity.kind == ACTIVITY_EVENT:
            await callback.answer("Это твоё событие 😄", show_alert=True)
        else:
            await callback.answer("Это твоя заявка 😄", show_alert=True)
        return

    member, action = await join_activity(
        session, activity=activity, user_id=user.id,
    )
    if action == "already":
        if member is not None and member.status == MEMBER_PENDING:
            await callback.answer("Заявка уже отправлена, ждёт подтверждения.", show_alert=True)
        else:
            await callback.answer("Ты уже в списке.", show_alert=False)
        return

    is_pending_action = action == "created_pending"

    if is_pending_action:
        await callback.answer("Заявка отправлена. Жди подтверждения 🙏", show_alert=False)
    elif activity.kind == ACTIVITY_EVENT:
        await callback.answer("Ты в списке участников!")
    else:
        await callback.answer("Отклик отправлен!")

    # Перерисовываем карточку через builder ленты — он сохранит
    # ряд навигации, кнопку фильтров и сам решит, какую primary-кнопку
    # показывать (joined → «Отписаться», pending → «Заявка отправлена»).
    await _rerender_feed_card(
        callback, session, user=user, activity=activity,
    )

    # Мгновенный invite в чат — только для подтверждённых.
    if not is_pending_action and activity.chat_url:
        try:
            await bot.send_message(
                callback.from_user.id,
                f"💬 Чат «{esc(activity.title)}»:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="💬 Открыть чат", url=activity.chat_url)],
                    ],
                ),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        await mark_member_notified(
            session, activity_id=activity.id, user_id=user.id,
        )

    # Уведомление организатору/автору с профилем нового участника.
    creator = await get_user_by_id(session, activity.creator_id)
    if creator and creator.id != user.id:
        await notify_creator_about_new_member(
            bot,
            recipient_tg_id=creator.telegram_id,
            member=user,
            activity=activity,
            is_pending=is_pending_action,
        )


# ──────────────────────────── leave / withdraw / remove response ─────────────


@router.callback_query(F.data.startswith("al:"))
async def on_leave(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    removed = await leave_activity(
        session, activity_id=activity_id, user_id=user.id,
    )
    if not removed:
        await callback.answer("Записи нет.", show_alert=False)
        return

    activity = await get_activity(session, activity_id)
    if activity is None:
        await callback.answer("Готово.")
        return

    if activity.kind == ACTIVITY_EVENT:
        await callback.answer("Ты отписался.")
    else:
        await callback.answer("Отклик убран.")

    if _is_profile_context(callback):
        # Из профиля — возвращаемся в хаб с обновлёнными счётчиками.
        await rerender_profile_to_hub(callback.message, session, user)
    else:
        # Из ленты — полная перерисовка через builder, чтобы сохранить
        # навигацию и кнопку фильтров.
        await _rerender_feed_card(
            callback, session, user=user, activity=activity,
        )


# ──────────────────────────── members / responders list ─────────────────────


@router.callback_query(F.data.startswith("amem:"))
async def on_members(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    activity = await get_activity(session, activity_id)
    if activity is None:
        await callback.answer("Не найдено", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    if activity.creator_id != user.id:
        await callback.answer("Только создатель может смотреть список.", show_alert=True)
        return

    joined_rows = await get_activity_members(
        session, activity_id=activity_id, status=MEMBER_JOINED,
    )
    pending_rows = await get_activity_members(
        session, activity_id=activity_id, status=MEMBER_PENDING,
    )
    if not joined_rows and not pending_rows:
        await callback.answer(_no_members_alert_text(activity.kind), show_alert=True)
        return

    lines = [_members_header(activity.kind, activity.title)]
    if joined_rows:
        if activity.visibility == VISIBILITY_PRIVATE:
            lines.append("\n<b>Подтверждённые:</b>")
        for i, (_, u) in enumerate(joined_rows, 1):
            name = esc(u.first_name or u.username or "—")
            username_part = f" @{esc(u.username)}" if u.username else ""
            age_part = f", {u.age} лет" if u.age else ""
            bio_part = f"\n   {esc((u.bio or '')[:80])}" if u.bio else ""
            tg_link = (
                f' <a href="tg://user?id={u.telegram_id}">написать</a>'
                if u.telegram_id
                else ""
            )
            lines.append(f"{i}. {name}{username_part}{age_part}{tg_link}{bio_part}")

    inline_rows: list[list[InlineKeyboardButton]] = []
    if pending_rows:
        lines.append("\n<b>Ждут подтверждения:</b>")
        for i, (_m, u) in enumerate(pending_rows, 1):
            name = esc(u.first_name or u.username or "—")
            username_part = f" @{esc(u.username)}" if u.username else ""
            age_part = f", {u.age} лет" if u.age else ""
            lines.append(f"⏳ {i}. {name}{username_part}{age_part}")
            inline_rows.append([
                InlineKeyboardButton(
                    text=f"✅ {name[:18]}",
                    callback_data=f"amap:{activity_id}:{u.id}",
                ),
                InlineKeyboardButton(
                    text=f"❌ {name[:18]}",
                    callback_data=f"amrj:{activity_id}:{u.id}",
                ),
            ])

    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows) if inline_rows else None
    await callback.message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )


# ──────────────────────────── approve / reject pending member ───────────────


@router.callback_query(F.data.startswith("amap:"))
async def on_approve_member(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        _, activity_id_raw, member_user_id_raw = callback.data.split(":", 2)
        activity_id = int(activity_id_raw)
        member_user_id = int(member_user_id_raw)
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    activity = await get_activity(session, activity_id)
    if activity is None:
        await callback.answer("Активность не найдена.", show_alert=True)
        return
    actor = await upsert_telegram_user(session, callback.from_user)
    if activity.creator_id != actor.id:
        await callback.answer("Только создатель может подтверждать.", show_alert=True)
        return

    ok = await approve_member(
        session, activity_id=activity_id, user_id=member_user_id,
    )
    if not ok:
        await callback.answer("Этой заявки уже нет.", show_alert=False)
        return

    member_user = await get_user_by_id(session, member_user_id)
    if member_user is not None:
        await notify_user_about_decision(
            bot,
            recipient_tg_id=member_user.telegram_id,
            activity=activity,
            approved=True,
            chat_url=activity.chat_url,
        )
        if activity.chat_url:
            await mark_member_notified(
                session, activity_id=activity_id, user_id=member_user_id,
            )

    await callback.answer("Подтверждено ✅")
    # Если callback пришёл из DM-карточки уведомления — снимаем кнопки.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


@router.callback_query(F.data.startswith("amrj:"))
async def on_reject_member(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        _, activity_id_raw, member_user_id_raw = callback.data.split(":", 2)
        activity_id = int(activity_id_raw)
        member_user_id = int(member_user_id_raw)
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    activity = await get_activity(session, activity_id)
    if activity is None:
        await callback.answer("Активность не найдена.", show_alert=True)
        return
    actor = await upsert_telegram_user(session, callback.from_user)
    if activity.creator_id != actor.id:
        await callback.answer("Только создатель может отклонять.", show_alert=True)
        return

    # Проверяем, что это была именно pending — чтобы случайно не выкинуть
    # уже подтверждённого участника тем же UI.
    membership = await get_user_membership(
        session, activity_id=activity_id, user_id=member_user_id,
    )
    if membership is None or membership.status != MEMBER_PENDING:
        await callback.answer("Этой заявки уже нет.", show_alert=False)
        return

    await reject_member(session, activity_id=activity_id, user_id=member_user_id)

    member_user = await get_user_by_id(session, member_user_id)
    if member_user is not None:
        await notify_user_about_decision(
            bot,
            recipient_tg_id=member_user.telegram_id,
            activity=activity,
            approved=False,
        )

    await callback.answer("Отклонено")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ──────────────────────────── cancel event ───────────────────────────────────


@router.callback_query(F.data.startswith("acan:"))
async def on_cancel(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    activity = await get_activity(session, activity_id)
    if activity is None or activity.creator_id != user.id:
        await callback.answer("Это не твоё событие.", show_alert=True)
        return

    # Собираем участников ДО смены статуса (чтобы знать кому слать).
    member_rows = await get_activity_members(session, activity_id=activity_id)
    targets: list[tuple[int, str]] = [
        (u.telegram_id, m.status) for m, u in member_rows
    ]

    cancelled = await cancel_activity(
        session, activity_id=activity_id, actor_id=user.id,
    )
    if not cancelled:
        await callback.answer("Не удалось отменить.", show_alert=True)
        return

    await callback.answer("Событие отменено.", show_alert=True)
    if _is_profile_context(callback):
        await rerender_profile_to_hub(callback.message, session, user)
    else:
        # Defensive fallback: если когда-то acan: будет вызван не из
        # профиля, помечаем сообщение и снимаем клавиатуру.
        try:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "") + "\n\n<i>🚫 Отменено</i>",
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

    # Шлём DM всем — и joined, и pending — что событие отменено.
    if targets:
        await notify_members_about_cancel(
            bot, activity=activity, members=targets,
        )


# ──────────────────────────── close seeking ──────────────────────────────────


@router.callback_query(F.data.startswith("aclose:"))
async def on_close(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    closed = await close_activity(
        session, activity_id=activity_id, actor_id=user.id,
    )
    if not closed:
        await callback.answer("Не удалось — это не твоя заявка.", show_alert=True)
        return

    await callback.answer("Заявка закрыта.", show_alert=True)
    if _is_profile_context(callback):
        await rerender_profile_to_hub(callback.message, session, user)
    else:
        try:
            await callback.message.edit_caption(
                caption=(callback.message.caption or "Заявка закрыта.") + "\n\n<i>🗑 Закрыта</i>",
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass


# ──────────────────────────── feed: members carousel ────────────────────────


def _feed_carousel_context(activity_id: int) -> CarouselContext:
    return CarouselContext(
        nav_cb_template=f"fmem:n:{activity_id}:{{idx}}",
        back_cb="fmem:x",
        back_label="❌ Закрыть",
    )


@router.callback_query(F.data.startswith("fmem:o:"))
async def on_feed_members_open(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Открыть карусель участников как отдельное фото-сообщение под
    карточкой ленты. Не трогает карточку — она остаётся там, где была,
    карусель появляется под ней и закрывается независимо."""
    if callback.message is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return

    context = _feed_carousel_context(activity_id)
    view = await build_member_carousel_view(
        session,
        activity_id=activity_id,
        member_index=0,
        context=context,
    )
    if view is None:
        await callback.answer("Пока никого нет.", show_alert=True)
        return
    photo_id, caption, kb = view

    if photo_id:
        await callback.message.answer_photo(
            photo=photo_id,
            caption=caption,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    else:
        # У участника не оказалось аватара — показываем текстом.
        await callback.message.answer(
            caption,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("fmem:n:"))
async def on_feed_members_nav(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Перелистывание карусели в фото-сообщении через edit_message_media."""
    if callback.message is None:
        await callback.answer()
        return
    # Формат: fmem:n:<activity_id>:<idx>
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Некорректные данные", show_alert=True)
        return
    try:
        activity_id = int(parts[2])
        idx = int(parts[3])
    except ValueError:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    context = _feed_carousel_context(activity_id)
    view = await build_member_carousel_view(
        session,
        activity_id=activity_id,
        member_index=idx,
        context=context,
    )
    if view is None:
        await callback.answer("Пусто.", show_alert=True)
        return
    photo_id, caption, kb = view

    try:
        if callback.message.photo and photo_id:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=photo_id,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                ),
                reply_markup=kb,
            )
        elif callback.message.photo:
            # У нового участника нет аватара — обновляем только caption,
            # фото предыдущего участника остаётся как есть.
            await callback.message.edit_caption(
                caption=caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
        else:
            # Fallback: если исходно отправляли текстом (не было аватара
            # у первого участника).
            await callback.message.edit_text(
                caption,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "fmem:x")
async def on_feed_members_close(callback: CallbackQuery) -> None:
    """Закрытие карусели — просто удаляем её сообщение. Карточка ленты
    остаётся нетронутой в чате выше."""
    if callback.message is None:
        await callback.answer()
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()
