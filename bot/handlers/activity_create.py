"""Создание Activity.

Точка входа — единая reply-кнопка «➕ Создать активность». Она
запускает мини-FSM `CreateActivitySG.kind`, где юзер inline-кнопкой
выбирает kind: «🎉 Организовать мероприятие» или «🤝 Найти компанию».
После выбора управление переходит в один из подфлоу:

- `CreateEventSG` — событие (6 шагов: title → description → starts_at →
  place → chat_url → tags). Visibility ставится по умолчанию `open`
  при создании, менять её можно потом в профиле (`activity_chat` /
  visibility manager).
- `CreateSeekingSG` — заявка (5 шагов: title → body → duration →
  chat_url → tags). Аналогично — visibility всегда `open` на старте.

Шаг выбора kind считаем «pre-step» и в нумерации шагов подфлоу не
участвует — поэтому event остаётся «Шаг N/6», а seeking «Шаг N/5».
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import BTN_CANCEL, cancel_keyboard, main_menu_reply
from bot.keyboards.tag_picker import tag_picker_keyboard
from bot.services.activities import create_event_draft, create_seeking_draft
from bot.services.tags import list_active_tags
from bot.services.users import upsert_telegram_user
from bot.utils.chat_link import InvalidChatLinkError, normalize_chat_link
from bot.utils.datetime_parse import parse_user_datetime_msk

router = Router(name="activity_create")


# ──────────────────────────── KIND DISPATCHER ────────────────────────────────


class CreateActivitySG(StatesGroup):
    """Pre-step перед основным FSM создания: пользователь выбирает,
    что он создаёт — событие или заявку «ищу компанию»."""

    kind = State()


CAK_EVENT_CB = "cak:event"
CAK_SEEKING_CB = "cak:seeking"


def _kind_picker_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎉 Организовать мероприятие",
                callback_data=CAK_EVENT_CB,
            )],
            [InlineKeyboardButton(
                text="🤝 Найти компанию для своего дела",
                callback_data=CAK_SEEKING_CB,
            )],
        ],
    )


async def start_create_activity(target: Message, state: FSMContext) -> None:
    """Точка входа из главного меню — показывает kind-пикер."""
    await state.set_state(CreateActivitySG.kind)
    await target.answer(
        "<b>Что хочешь?</b>\n\n"
        "🎉 <b>Организовать мероприятие</b> — создать событие на дату и место, "
        "люди записываются.\n"
        "🤝 <b>Найти компанию для своего дела</b> — заявка типа «ищу с кем "
        "сходить», другие откликаются.",
        reply_markup=_kind_picker_kb(),
        parse_mode=ParseMode.HTML,
    )
    # Показываем reply-кнопку «❌ Отменить» поверх главного меню,
    # чтобы можно было выйти из выбора kind, как из любого FSM.
    await target.answer(
        "Отмена в любой момент: «❌ Отменить» или /cancel",
        reply_markup=cancel_keyboard(),
    )


@router.message(
    or_f(Command("cancel"), F.text == BTN_CANCEL),
    StateFilter(CreateActivitySG),
)
async def kind_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание отменено.", reply_markup=main_menu_reply())


@router.callback_query(
    F.data == CAK_EVENT_CB,
    StateFilter(CreateActivitySG.kind),
)
async def on_pick_event(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    # Снимаем inline-клавиатуру с предыдущего сообщения, чтобы по нему
    # нельзя было кликнуть повторно после выбора.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _start_event_creation(callback.message, state)
    await callback.answer()


@router.callback_query(
    F.data == CAK_SEEKING_CB,
    StateFilter(CreateActivitySG.kind),
)
async def on_pick_seeking(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _start_seeking_creation(callback.message, state)
    await callback.answer()


# ──────────────────────────── EVENT FSM ──────────────────────────────────────


async def _start_event_creation(target: Message, state: FSMContext) -> None:
    """Старт event-подфлоу. Зовётся как из dispatcher kind-выбора, так и
    отовсюду, где нужно открыть создание события напрямую."""
    await state.set_state(CreateEventSG.title)
    await target.answer(
        "Создаём событие. Шаг 1/7: <b>название</b> (до 120 символов).",
        reply_markup=cancel_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def start_create_from_template(
    target: Message,
    state: FSMContext,
    template,
) -> None:
    """Создание события с предзаполненными данными из шаблона.

    Предзаполняем title, place, description, cover.
    Юзеру остаётся: обложка (сменить/оставить) → дата → чат → теги.
    """
    await state.clear()
    data: dict = {
        "title": template.title,
        "place_text": template.place_text,
        "template_id": template.id,
        "_from_template": True,
    }
    if template.description:
        data["description"] = template.description
    if template.cover_file_id:
        data["cover_file_id"] = template.cover_file_id

    await state.update_data(data)
    await state.set_state(CreateEventSG.cover)

    from bot.utils.formatting import esc
    place_info = f"\n📍 {esc(template.place_text)}" if template.place_text else ""
    cover_hint = "Обложка из шаблона — можешь заменить фото или пропустить." if template.cover_file_id else "Отправь фото обложки или пропусти."
    await target.answer(
        f"Создаём событие: <b>{esc(template.title)}</b>{place_info}\n\n"
        f"{cover_hint}",
        reply_markup=_skip_kb(CE_COVER_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


class CreateEventSG(StatesGroup):
    title = State()
    cover = State()
    description = State()
    starts_at = State()
    place = State()
    chat_url = State()
    tags = State()


CT_E_PREFIX = "ct:e"
CT_E_TMP_KEY = "create_event_tag_ids"
CE_CHAT_SKIP_CB = "cecu:skip"
CE_COVER_SKIP_CB = "cecv:skip"


def _skip_kb(skip_cb: str) -> InlineKeyboardMarkup:
    """Inline-клавиатура с одной кнопкой «⏭ Пропустить» — используется
    на необязательных шагах FSM (chat_url, cover)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data=skip_cb)],
        ],
    )


# Совместимость на время рефакторинга — старое имя ссылается на новое.
_chat_url_prompt_kb = _skip_kb


async def _render_event_tags_step(
    message: Message,
    session: AsyncSession,
    *,
    selected_ids: set[int],
) -> None:
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags,
        selected_ids=selected_ids,
        prefix=CT_E_PREFIX,
        with_done=True,
    )
    await message.answer(
        "Шаг 7/7: <b>выбери теги</b> (минимум один). "
        "Нажми на тег, чтобы отметить, и «✅ Готово» когда выберешь.",
        reply_markup=kb,
    )


@router.message(or_f(Command("cancel"), F.text == BTN_CANCEL), StateFilter(CreateEventSG))
async def event_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание события отменено.", reply_markup=main_menu_reply())


@router.message(CreateEventSG.title, F.text)
async def event_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 3:
        await message.answer("Слишком коротко. Напиши название хотя бы из 3 символов.")
        return
    if len(title) > 120:
        title = title[:120]
    await state.update_data(title=title)
    await state.set_state(CreateEventSG.cover)
    await message.answer(
        "Шаг 2/7: <b>обложка</b> — пришли картинку для события.\n\n"
        "Можно пропустить — тогда покажем стандартную.",
        reply_markup=_skip_kb(CE_COVER_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateEventSG.cover, F.photo)
async def event_cover_photo(message: Message, state: FSMContext) -> None:
    photos = message.photo or []
    if not photos:
        await message.answer(
            "Жду фото. Можешь пропустить — кнопка ниже.",
            reply_markup=_skip_kb(CE_COVER_SKIP_CB),
        )
        return
    await state.update_data(cover_file_id=photos[-1].file_id)
    data = await state.get_data()
    if data.get("_from_template"):
        await state.set_state(CreateEventSG.starts_at)
        await message.answer(
            "Дата и время начала (Москва).\n"
            "Примеры: 25.04.2026 19:00 или 2026-04-25 19:00",
        )
    else:
        await state.set_state(CreateEventSG.description)
        await message.answer("Шаг 3/7: <b>описание</b> (можно одним сообщением).")


@router.message(CreateEventSG.cover)
async def event_cover_wrong(message: Message) -> None:
    await message.answer(
        "Жду <b>фото</b>. Если не хочешь — нажми «⏭ Пропустить».",
        reply_markup=_skip_kb(CE_COVER_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == CE_COVER_SKIP_CB, StateFilter(CreateEventSG.cover))
async def event_cover_skip(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    if not data.get("cover_file_id"):
        await state.update_data(cover_file_id=None)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if data.get("_from_template"):
        await state.set_state(CreateEventSG.starts_at)
        await callback.message.answer(
            "Дата и время начала (Москва).\n"
            "Примеры: 25.04.2026 19:00 или 2026-04-25 19:00",
        )
        await callback.answer()
    else:
        await state.set_state(CreateEventSG.description)
        await callback.message.answer(
            "Шаг 3/7: <b>описание</b> (можно одним сообщением).",
            parse_mode=ParseMode.HTML,
        )
        await callback.answer("Используем стандартную обложку")


@router.message(CreateEventSG.description, F.text)
async def event_description(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    if len(desc) < 5:
        await message.answer("Добавь чуть больше деталей в описание (от 5 символов).")
        return
    await state.update_data(description=desc[:4000])
    await state.set_state(CreateEventSG.starts_at)
    await message.answer(
        "Шаг 4/7: <b>дата и время начала</b> (Москва).\n"
        "Примеры: <code>25.04.2026 19:00</code> или <code>2026-04-25 19:00</code>",
    )


@router.message(CreateEventSG.starts_at, F.text)
async def event_starts(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        starts_at = parse_user_datetime_msk(raw)
    except ValueError as e:
        await message.answer(str(e))
        return
    await state.update_data(starts_at_iso=starts_at.isoformat())
    data = await state.get_data()
    if data.get("_from_template") and data.get("place_text"):
        # Место уже из шаблона — пропускаем
        await state.set_state(CreateEventSG.chat_url)
        await message.answer(
            "Ссылка на чат события (например, <code>https://t.me/...</code>).\n\n"
            "Можно пропустить и добавить позже.",
            reply_markup=_skip_kb(CE_CHAT_SKIP_CB),
            parse_mode=ParseMode.HTML,
        )
    else:
        await state.set_state(CreateEventSG.place)
        await message.answer(
            "Шаг 5/7: <b>место</b> — напиши адрес или скинь ссылку из Яндекс Карт.",
            parse_mode=ParseMode.HTML,
        )


@router.callback_query(F.data.startswith("place:pick:"), StateFilter(CreateEventSG.place))
async def event_place_pick(callback: CallbackQuery, state: FSMContext) -> None:
    """Юзер выбрал адрес из подсказок Dadata."""
    if callback.message is None:
        await callback.answer()
        return
    idx_raw = callback.data.split(":", 2)[2]
    try:
        idx = int(idx_raw)
    except ValueError:
        await callback.answer()
        return

    data = await state.get_data()
    suggestions = data.get("_place_suggestions", [])
    if idx < 0 or idx >= len(suggestions):
        await callback.answer()
        return
    place = suggestions[idx]
    await state.update_data(place_text=place[:500])
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.set_state(CreateEventSG.chat_url)
    await callback.message.answer(
        "Шаг 6/7: <b>ссылка на чат события</b> (например, "
        "<code>https://t.me/...</code>) — чтобы участники сразу могли попасть в обсуждение.\n\n"
        "Можно пропустить и добавить позже в профиле.",
        reply_markup=_skip_kb(CE_CHAT_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "place:retry", StateFilter(CreateEventSG.place))
async def event_place_retry(callback: CallbackQuery) -> None:
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Напиши адрес заново:")


@router.callback_query(F.data == "place:keep", StateFilter(CreateEventSG.place))
async def event_place_keep(callback: CallbackQuery, state: FSMContext) -> None:
    """Юзер оставляет свой текст как есть."""
    if callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    raw = data.get("_place_raw", "")
    if not raw:
        await callback.answer("Напиши адрес заново.")
        return
    await state.update_data(place_text=raw[:500])
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await state.set_state(CreateEventSG.chat_url)
    await callback.message.answer(
        "Шаг 6/7: <b>ссылка на чат события</b> (например, "
        "<code>https://t.me/...</code>) — чтобы участники сразу могли попасть в обсуждение.\n\n"
        "Можно пропустить и добавить позже в профиле.",
        reply_markup=_skip_kb(CE_CHAT_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateEventSG.place, F.text)
async def event_place(message: Message, state: FSMContext) -> None:
    from bot.config import get_settings
    from bot.services.place_suggest import suggest_places
    from bot.utils.maps import extract_place_from_url, is_maps_url

    raw = (message.text or "").strip()

    # Ссылка на карты
    if is_maps_url(raw):
        place = await extract_place_from_url(raw)
        if not place:
            await message.answer(
                "Не удалось распознать место из ссылки. "
                "Напиши название текстом или попробуй другую ссылку.",
            )
            return
        await state.update_data(place_text=place[:500])
        await state.set_state(CreateEventSG.chat_url)
        await message.answer(
            "Шаг 6/7: <b>ссылка на чат события</b> (например, "
            "<code>https://t.me/...</code>) — чтобы участники сразу могли попасть в обсуждение.\n\n"
            "Можно пропустить и добавить позже в профиле.",
            reply_markup=_skip_kb(CE_CHAT_SKIP_CB),
            parse_mode=ParseMode.HTML,
        )
        return

    if len(raw) < 2:
        await message.answer("Укажи место чуть подробнее.")
        return

    # Подсказки 2GIS (организации и места)
    api_key = get_settings().twogis_api_key
    if api_key:
        suggestions = await suggest_places(raw, api_key, count=4)
        if suggestions:
            fulls = [s.full for s in suggestions]
            await state.update_data(_place_suggestions=fulls, _place_raw=raw)
            rows = [
                [InlineKeyboardButton(
                    text=s.name[:60],
                    callback_data=f"place:pick:{i}",
                )]
                for i, s in enumerate(suggestions)
            ]
            keep_label = f"✅ Оставить «{raw[:30]}»"
            rows.append([InlineKeyboardButton(text=keep_label, callback_data="place:keep")])
            rows.append([InlineKeyboardButton(text="✏️ Ввести заново", callback_data="place:retry")])
            await message.answer(
                "Выбери место или оставь как есть:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            )
            return

    # Без API или нет подсказок — берём как есть
    await state.update_data(place_text=raw[:500])
    await state.set_state(CreateEventSG.chat_url)
    await message.answer(
        "Шаг 6/7: <b>ссылка на чат события</b> (например, "
        "<code>https://t.me/...</code>) — чтобы участники сразу могли попасть в обсуждение.\n\n"
        "Можно пропустить и добавить позже в профиле.",
        reply_markup=_skip_kb(CE_CHAT_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateEventSG.chat_url, F.text)
async def event_chat_url(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = message.text or ""
    try:
        link = normalize_chat_link(raw)
    except InvalidChatLinkError as e:
        await message.answer(
            str(e),
            reply_markup=_chat_url_prompt_kb(CE_CHAT_SKIP_CB),
            parse_mode=ParseMode.HTML,
        )
        return
    await state.update_data(chat_url=link, **{CT_E_TMP_KEY: []})
    await state.set_state(CreateEventSG.tags)
    await _render_event_tags_step(message, session, selected_ids=set())


@router.callback_query(F.data == CE_CHAT_SKIP_CB, StateFilter(CreateEventSG.chat_url))
async def event_chat_url_skip(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await state.update_data(chat_url=None, **{CT_E_TMP_KEY: []})
    await state.set_state(CreateEventSG.tags)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _render_event_tags_step(callback.message, session, selected_ids=set())
    await callback.answer("Пропущено — добавишь позже в профиле")


@router.callback_query(
    F.data.startswith(f"{CT_E_PREFIX}:t:"),
    StateFilter(CreateEventSG.tags),
)
async def event_tags_toggle(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    try:
        tag_id = int(callback.data.split(":", 3)[3])
    except (IndexError, ValueError):
        await callback.answer("Некорректные данные", show_alert=True)
        return
    data = await state.get_data()
    current = set(data.get(CT_E_TMP_KEY) or [])
    if tag_id in current:
        current.remove(tag_id)
    else:
        current.add(tag_id)
    await state.update_data({CT_E_TMP_KEY: sorted(current)})
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags, selected_ids=current, prefix=CT_E_PREFIX, with_done=True,
    )
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass
    await callback.answer()


@router.callback_query(
    F.data == f"{CT_E_PREFIX}:done",
    StateFilter(CreateEventSG.tags),
)
async def event_tags_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    data = await state.get_data()
    tag_ids = list(data.get(CT_E_TMP_KEY) or [])
    if not tag_ids:
        await callback.answer("Выбери хотя бы один тег", show_alert=True)
        return

    title = data.get("title")
    description = data.get("description")
    starts_raw = data.get("starts_at_iso")
    place_text = data.get("place_text")
    chat_url = data.get("chat_url")
    cover_file_id = data.get("cover_file_id")
    if not title or not description or not starts_raw or not place_text:
        await state.clear()
        await callback.message.answer(
            "Что-то пошло не так с черновиком. Начни снова: «➕ Создать активность».",
            reply_markup=main_menu_reply(),
        )
        await callback.answer()
        return

    starts_at = datetime.fromisoformat(starts_raw)
    user = await upsert_telegram_user(session, callback.from_user)
    await create_event_draft(
        session,
        creator_id=user.id,
        city_id=user.city_id,
        title=title,
        description=description,
        starts_at=starts_at,
        place_text=place_text,
        chat_url=chat_url,
        cover_file_id=cover_file_id,
        tag_ids=tag_ids,
        template_id=data.get("template_id"),
    )
    await state.clear()
    await callback.message.answer(
        "Событие отправлено на <b>ручную проверку</b>. После модерации оно появится в ленте.",
        reply_markup=main_menu_reply(),
    )
    await callback.answer()


# ──────────────────────────── SEEKING FSM ────────────────────────────────────


class CreateSeekingSG(StatesGroup):
    title = State()
    cover = State()
    body = State()
    duration = State()
    chat_url = State()
    tags = State()


CT_S_PREFIX = "ct:s"
CT_S_TMP_KEY = "create_seeking_tag_ids"
CS_CHAT_SKIP_CB = "cscu:skip"
CS_COVER_SKIP_CB = "cscv:skip"


async def _start_seeking_creation(target: Message, state: FSMContext) -> None:
    """Запуск seeking-FSM из меню или из callback-кнопки."""
    await state.set_state(CreateSeekingSG.title)
    await target.answer(
        "Создаём заявку «ищу компанию».\n\n"
        "<b>Шаг 1/6</b>: коротко — <b>что хочешь сделать?</b>\n"
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


@router.message(or_f(Command("cancel"), F.text == BTN_CANCEL), StateFilter(CreateSeekingSG))
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
    await state.set_state(CreateSeekingSG.cover)
    await message.answer(
        "<b>Шаг 2/6</b>: <b>обложка</b> — пришли картинку для заявки.\n\n"
        "Можно пропустить — тогда покажем стандартную.",
        reply_markup=_skip_kb(CS_COVER_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateSeekingSG.cover, F.photo)
async def seeking_cover_photo(message: Message, state: FSMContext) -> None:
    photos = message.photo or []
    if not photos:
        await message.answer(
            "Жду фото. Можешь пропустить — кнопка ниже.",
            reply_markup=_skip_kb(CS_COVER_SKIP_CB),
        )
        return
    await state.update_data(cover_file_id=photos[-1].file_id)
    await state.set_state(CreateSeekingSG.body)
    await message.answer(
        "<b>Шаг 3/6</b>: расскажи <b>подробнее</b> — когда, с кем, что важно.\n"
        "Можно коротко, можно развёрнуто.",
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateSeekingSG.cover)
async def seeking_cover_wrong(message: Message) -> None:
    await message.answer(
        "Жду <b>фото</b>. Если не хочешь — нажми «⏭ Пропустить».",
        reply_markup=_skip_kb(CS_COVER_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == CS_COVER_SKIP_CB, StateFilter(CreateSeekingSG.cover))
async def seeking_cover_skip(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await state.update_data(cover_file_id=None)
    await state.set_state(CreateSeekingSG.body)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "<b>Шаг 3/6</b>: расскажи <b>подробнее</b> — когда, с кем, что важно.\n"
        "Можно коротко, можно развёрнуто.",
        parse_mode=ParseMode.HTML,
    )
    await callback.answer("Используем стандартную обложку")


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
        "<b>Шаг 4/6</b>: сколько дней будет актуальна заявка?",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("skd:"), StateFilter(CreateSeekingSG.duration))
async def seeking_duration(callback: CallbackQuery, state: FSMContext) -> None:
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
        "<b>Шаг 5/6</b>: пришли <b>ссылку на чат заявки</b> "
        "(например, <code>https://t.me/...</code>), чтобы откликнувшиеся "
        "сразу могли попасть в обсуждение.\n\n"
        "Можно пропустить и добавить позже в профиле.",
        reply_markup=_skip_kb(CS_CHAT_SKIP_CB),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


async def _render_seeking_tags_step(
    message: Message, session: AsyncSession, *, selected_ids: set[int],
) -> None:
    tags = await list_active_tags(session)
    kb = tag_picker_keyboard(
        tags=tags, selected_ids=selected_ids, prefix=CT_S_PREFIX, with_done=True,
    )
    await message.answer(
        "<b>Шаг 6/6</b>: выбери теги (минимум один). "
        "Нажми на тег, чтобы отметить, и «✅ Готово» когда выберешь.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.message(CreateSeekingSG.chat_url, F.text)
async def seeking_chat_url(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = message.text or ""
    try:
        link = normalize_chat_link(raw)
    except InvalidChatLinkError as e:
        await message.answer(
            str(e),
            reply_markup=_chat_url_prompt_kb(CS_CHAT_SKIP_CB),
            parse_mode=ParseMode.HTML,
        )
        return
    await state.update_data(chat_url=link, **{CT_S_TMP_KEY: []})
    await state.set_state(CreateSeekingSG.tags)
    await _render_seeking_tags_step(message, session, selected_ids=set())


@router.callback_query(F.data == CS_CHAT_SKIP_CB, StateFilter(CreateSeekingSG.chat_url))
async def seeking_chat_url_skip(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
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
    await callback.answer("Пропущено — добавишь позже в профиле")


@router.callback_query(
    F.data.startswith(f"{CT_S_PREFIX}:t:"),
    StateFilter(CreateSeekingSG.tags),
)
async def seeking_tags_toggle(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
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
        tags=tags, selected_ids=current, prefix=CT_S_PREFIX, with_done=True,
    )
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass
    await callback.answer()


@router.callback_query(
    F.data == f"{CT_S_PREFIX}:done",
    StateFilter(CreateSeekingSG.tags),
)
async def seeking_tags_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
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
    cover_file_id = data.get("cover_file_id")
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
        creator_id=user.id,
        city_id=user.city_id,
        title=title,
        body=body,
        expires_at=expires_at,
        chat_url=chat_url,
        cover_file_id=cover_file_id,
        tag_ids=tag_ids,
    )
    await state.clear()
    await callback.message.answer(
        "Заявка отправлена на <b>проверку</b>. После модерации появится в разделе «🤝 Найти компанию».",
        reply_markup=main_menu_reply(),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()
