from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from bot.constants import MOSCOW_CITY_ID, SEEKING_PUBLISHED
from bot.handlers.profile import ProfileSG, begin_profile_flow
from bot.keyboards.main_menu import BTN_CANCEL, cancel_keyboard, main_menu_reply
from bot.keyboards.tag_picker import format_tags_inline, tag_picker_keyboard
from bot.models import User
from bot.services.chat_invite_notify import mark_response_notified
from bot.services.company_seeking import (
    close_seeking,
    count_responses,
    create_seeking_draft,
    get_author,
    get_seeking,
    get_seeking_responders,
    is_user_responded_seeking,
    list_published_seekings,
    user_responded,
)
from bot.services.notifications import notify_actor_about_new_member
from bot.services.profile_view import rerender_profile_card
from bot.services.search_prefs import get_seeking_tag_filter
from bot.services.tags import get_tags_by_ids, list_active_tags
from bot.services.users import is_profile_complete, upsert_telegram_user, upsert_user_from_message
from bot.utils.chat_link import InvalidChatLinkError, normalize_chat_link
from bot.utils.formatting import esc, format_datetime_msk

router = Router(name="company_seeking")


# ──────────────────────────── FSM создания заявки ────────────────────────────

class CreateSeekingSG(StatesGroup):
    title = State()
    body = State()
    duration = State()
    chat_url = State()
    tags = State()


CS_CHAT_SKIP_CB = "cscu:skip"


def _seeking_chat_url_prompt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data=CS_CHAT_SKIP_CB)],
        ],
    )


# ──────────────────────────── helpers ────────────────────────────────────────

def _seeking_text(
    seeking,
    *,
    author,
    responses: int,
    active_filter=None,
) -> str:
    name = esc(author.first_name or author.username or "Аноним") if author else "Аноним"
    age_str = f", {author.age} лет" if author and author.age else ""
    header = "<b>Ищут компанию · Москва</b>"
    if active_filter:
        header += f"\n<i>🔎 фильтр: {esc(format_tags_inline(active_filter))}</i>"
    lines = [
        header,
        "",
        f"<b>{esc(seeking.title)}</b>",
        f"👤 {name}{age_str}",
        f"⏳ до {format_datetime_msk(seeking.expires_at)}",
        f"🙋 Откликов: {responses}",
    ]
    if seeking.tags:
        lines.append(f"🏷 {esc(format_tags_inline(list(seeking.tags)))}")
    if seeking.body:
        lines += ["", esc(seeking.body)]
    return "\n".join(lines)


def _feed_keyboard(
    idx: int,
    total: int,
    seeking_id: int,
    *,
    chat_url: str | None = None,
    viewer_responded: bool = False,
) -> InlineKeyboardMarkup:
    prev = f"sk:g:{max(0, idx - 1)}"
    nxt = f"sk:g:{min(total - 1, idx + 1)}"
    mid = f"sk:c:{idx}"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="⬅️", callback_data=prev),
            InlineKeyboardButton(text=f"{idx + 1} / {total}", callback_data=mid),
            InlineKeyboardButton(text="➡️", callback_data=nxt),
        ],
        [InlineKeyboardButton(text="Хочу ✅", callback_data=f"sr:{seeking_id}")],
    ]
    if viewer_responded and chat_url:
        rows.append([InlineKeyboardButton(text="💬 Чат заявки", url=chat_url)])
    rows.append(
        [InlineKeyboardButton(text="🔎 Фильтры", callback_data="tp:s:open")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_feed_view(
    session: AsyncSession,
    index: int,
    *,
    tag_ids: list[int] | None = None,
    viewer_user_id: int | None = None,
):
    seekings = await list_published_seekings(session, tag_ids=tag_ids)
    if not seekings:
        return None
    idx = max(0, min(index, len(seekings) - 1))
    s = seekings[idx]
    author = await get_author(session, s)
    n = await count_responses(session, s.id)
    active_filter = await get_tags_by_ids(session, tag_ids) if tag_ids else []
    responded = False
    if viewer_user_id is not None:
        responded = await is_user_responded_seeking(
            session, seeking_id=s.id, user_id=viewer_user_id,
        )
    text = _seeking_text(s, author=author, responses=n, active_filter=active_filter)
    kb = _feed_keyboard(
        idx,
        len(seekings),
        s.id,
        chat_url=s.chat_url,
        viewer_responded=responded,
    )
    return text, kb


# ──────────────────────────── лента ──────────────────────────────────────────

@router.callback_query(F.data.startswith("sk:g:"))
async def on_feed_page(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        idx = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_seeking_tag_filter(user)
    view = await build_feed_view(
        session, idx, tag_ids=ids or None, viewer_user_id=user.id,
    )
    if view is None:
        await callback.answer("Заявок больше нет", show_alert=True)
        return
    text, kb = view
    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("sk:c:"))
async def on_feed_counter(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None:
        await callback.answer()
        return
    try:
        idx = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    ids = get_seeking_tag_filter(user)
    seekings = await list_published_seekings(session, tag_ids=ids or None)
    if not seekings:
        await callback.answer()
        return
    await callback.answer(f"{idx + 1} из {len(seekings)}", show_alert=True)


# ──────────────────────────── отклик ─────────────────────────────────────────

@router.callback_query(F.data.startswith("sr:"))
async def on_respond(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        seeking_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    seeking = await get_seeking(session, seeking_id)
    if seeking is None or seeking.status != SEEKING_PUBLISHED:
        await callback.answer("Заявка уже недоступна", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)

    if not is_profile_complete(user):
        current = await state.get_state()
        if current is not None and current.startswith(ProfileSG.__name__):
            # Анкета уже идёт — просто обновляем цель, не перезапускаем с нуля
            await state.update_data({"pending_seek_id": seeking_id, "pending_join_event_id": None})
            await callback.answer("Ок — после анкеты откликнемся на эту заявку.", show_alert=False)
        else:
            await begin_profile_flow(
                callback.message,
                state,
                pending_event_id=None,
                pending_seeking_id=seeking_id,
            )
            await callback.answer("Сначала анкету — смотри в чате 👇")
        return

    if user.id == seeking.author_id:
        await callback.answer("Это твоя заявка 😄", show_alert=True)
        return

    added = await user_responded(session, seeking_id=seeking_id, user_id=user.id)
    if not added:
        author = await get_author(session, seeking)
        author_name = esc(author.first_name or author.username or "автор") if author else "автор"
        await callback.answer(
            f"Ты уже откликнулся ✅\n{author_name} получил уведомление с твоим профилем и кнопкой написать тебе.",
            show_alert=True,
        )
        return

    await callback.answer("Отклик отправлен! Автор получит уведомление.")

    # Если у заявки уже есть чат — сразу даём ссылку пользователю
    # и помечаем отклик как «получил приглашение».
    if seeking.chat_url:
        try:
            await bot.send_message(
                callback.from_user.id,
                f"💬 Чат заявки «{esc(seeking.title)}»:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="💬 Открыть чат", url=seeking.chat_url)],
                    ],
                ),
                disable_web_page_preview=True,
            )
        except Exception:
            pass
        await mark_response_notified(session, seeking_id=seeking_id, user_id=user.id)

    author = await get_author(session, seeking)
    if author:
        await notify_actor_about_new_member(
            bot,
            recipient_tg_id=author.telegram_id,
            member=user,
            entity_title=seeking.title,
            entity_kind="seeking",
        )


# ──────────────────────────── отклики на заявку (для автора) ─────────────────

@router.callback_query(F.data.startswith("skp:"))
async def on_seeking_responders(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        seeking_id = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    seeking = await get_seeking(session, seeking_id)
    if seeking is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    if seeking.author_id != user.id:
        await callback.answer("Только автор может смотреть отклики.", show_alert=True)
        return

    rows = await get_seeking_responders(session, seeking_id=seeking_id)
    if not rows:
        await callback.answer("Пока нет откликов.", show_alert=True)
        return

    lines = [f"<b>Отклики на «{esc(seeking.title)}»:</b>"]
    for i, (_, u) in enumerate(rows, 1):
        name = esc(u.first_name or u.username or "—")
        username_part = f" @{esc(u.username)}" if u.username else ""
        age_part = f", {u.age} лет" if u.age else ""
        bio_part = f"\n   {esc((u.bio or '')[:80])}" if u.bio else ""
        tg_link = f' <a href="tg://user?id={u.telegram_id}">написать</a>' if u.telegram_id else ""
        lines.append(f"{i}. {name}{username_part}{age_part}{tg_link}{bio_part}")

    await callback.answer()
    await callback.message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ──────────────────────────── закрыть свою заявку ────────────────────────────

@router.callback_query(F.data.startswith("sk:close:"))
async def on_seeking_close(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        seeking_id = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return

    user = await upsert_telegram_user(session, callback.from_user)
    closed = await close_seeking(session, seeking_id=seeking_id, author_id=user.id)
    if closed:
        await callback.answer("Заявка закрыта.", show_alert=True)
        if callback.message.photo:
            # Из профиля — перерисовываем карточку; закрытая заявка
            # пропадёт из «Мои заявки».
            await rerender_profile_card(callback.message, session, user)
        else:
            await callback.message.edit_text(
                (callback.message.text or "Заявка закрыта.") + "\n\n<i>🗑 Заявка закрыта</i>",
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
    else:
        await callback.answer("Не удалось закрыть — возможно, это не твоя заявка.", show_alert=True)


# ──────────────────────────── FSM создания ───────────────────────────────────

async def _start_seeking_creation(target: Message, state: FSMContext) -> None:
    """Общий хелпер запуска FSM: и из меню, и из callback."""
    await state.set_state(CreateSeekingSG.title)
    await target.answer(
        "Создаём заявку «ищу компанию».\n\n"
        "<b>Шаг 1/5</b>: коротко — <b>что хочешь сделать?</b>\n"
        "Например: «Сходить в кино», «Поиграть в настолки».",
        reply_markup=cancel_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "sk:create")
async def on_create_start_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await _start_seeking_creation(callback.message, state)
    await callback.answer()


@router.message(
    (Command("cancel") | F.text == BTN_CANCEL),
    StateFilter(CreateSeekingSG),
)
async def seeking_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание заявки отменено.", reply_markup=main_menu_reply())


@router.message(CreateSeekingSG.title, F.text)
async def seeking_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Слишком коротко — минимум 3 символа.")
        return
    if len(title) > 120:
        title = title[:120]
    await state.update_data(title=title)
    await state.set_state(CreateSeekingSG.body)
    await message.answer(
        "<b>Шаг 2/5</b>: расскажи <b>подробнее</b> — когда, с кем, что важно.\n"
        "Можно коротко, можно развёрнуто.",
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateSeekingSG.body, F.text)
async def seeking_body(message: Message, state: FSMContext) -> None:
    body = (message.text or "").strip()
    if len(body) < 5:
        await message.answer("Добавь чуть больше деталей (минимум 5 символов).")
        return
    await state.update_data(body=body[:3000])
    await state.set_state(CreateSeekingSG.duration)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 день", callback_data="skd:1"),
                InlineKeyboardButton(text="3 дня", callback_data="skd:3"),
                InlineKeyboardButton(text="7 дней", callback_data="skd:7"),
            ]
        ]
    )
    await message.answer(
        "<b>Шаг 3/5</b>: сколько дней будет актуальна заявка?",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


CT_S_PREFIX = "ct:s"
CT_S_TMP_KEY = "create_seeking_tag_ids"


async def _render_seeking_tags_step(
    message: Message,
    session: AsyncSession,
    *,
    selected_ids: set[int],
) -> None:
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=selected_ids,
        prefix=CT_S_PREFIX,
        with_done=True,
    )
    await message.answer(
        "<b>Шаг 5/5</b>: выбери теги (минимум один). "
        "Нажми на тег, чтобы отметить, и «✅ Готово» когда выберешь.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("skd:"), StateFilter(CreateSeekingSG.duration))
async def seeking_duration(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    try:
        days = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Ошибка", show_alert=True)
        return

    data = await state.get_data()
    title = data.get("title")
    body = data.get("body")
    if not title or not body:
        await state.clear()
        await callback.message.answer("Данные потерялись. Начни снова.", reply_markup=main_menu_reply())
        await callback.answer()
        return

    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    await state.update_data(expires_at_iso=expires_at.isoformat())
    await state.set_state(CreateSeekingSG.chat_url)
    await callback.message.answer(
        "<b>Шаг 4/5</b>: пришли <b>ссылку на чат заявки</b> "
        "(например, <code>https://t.me/...</code>), чтобы откликнувшиеся сразу "
        "могли попасть в обсуждение.\n\n"
        "Можно пропустить и добавить позже в профиле.",
        reply_markup=_seeking_chat_url_prompt_kb(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.message(CreateSeekingSG.chat_url, F.text)
async def seeking_chat_url(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    raw = message.text or ""
    try:
        link = normalize_chat_link(raw)
    except InvalidChatLinkError as e:
        await message.answer(
            str(e),
            reply_markup=_seeking_chat_url_prompt_kb(),
            parse_mode=ParseMode.HTML,
        )
        return
    await state.update_data(chat_url=link, **{CT_S_TMP_KEY: []})
    await state.set_state(CreateSeekingSG.tags)
    await _render_seeking_tags_step(message, session, selected_ids=set())


@router.callback_query(
    F.data == CS_CHAT_SKIP_CB,
    StateFilter(CreateSeekingSG.chat_url),
)
async def seeking_chat_url_skip(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await state.update_data(chat_url=None, **{CT_S_TMP_KEY: []})
    await state.set_state(CreateSeekingSG.tags)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _render_seeking_tags_step(callback.message, session, selected_ids=set())
    await callback.answer("Пропущено — можно добавить позже в профиле")


@router.callback_query(
    F.data.startswith(f"{CT_S_PREFIX}:t:"),
    StateFilter(CreateSeekingSG.tags),
)
async def seeking_tags_toggle(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    try:
        tag_id = int(callback.data.split(":", 3)[3])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    data = await state.get_data()
    current = set(data.get(CT_S_TMP_KEY) or [])
    if tag_id in current:
        current.remove(tag_id)
    else:
        current.add(tag_id)
    await state.update_data({CT_S_TMP_KEY: sorted(current)})
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=current,
        prefix=CT_S_PREFIX,
        with_done=True,
    )
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer()


@router.callback_query(
    F.data == f"{CT_S_PREFIX}:done",
    StateFilter(CreateSeekingSG.tags),
)
async def seeking_tags_done(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    tag_ids = list(data.get(CT_S_TMP_KEY) or [])
    if not tag_ids:
        await callback.answer("Выбери хотя бы один тег", show_alert=True)
        return

    title = data.get("title")
    body = data.get("body")
    expires_raw = data.get("expires_at_iso")
    chat_url = data.get("chat_url")
    if not title or not body or not expires_raw:
        await state.clear()
        await callback.message.answer(
            "Данные потерялись. Начни снова.",
            reply_markup=main_menu_reply(),
        )
        await callback.answer()
        return

    expires_at = datetime.fromisoformat(expires_raw)
    user = await upsert_telegram_user(session, callback.from_user)
    await create_seeking_draft(
        session,
        author_id=user.id,
        city_id=MOSCOW_CITY_ID,
        title=title,
        body=body,
        expires_at=expires_at,
        chat_url=chat_url,
        tag_ids=tag_ids,
    )
    await state.clear()
    await callback.message.answer(
        "Заявка отправлена на <b>проверку</b>. После модерации появится в разделе «🤝 Найти компанию».",
        reply_markup=main_menu_reply(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()
