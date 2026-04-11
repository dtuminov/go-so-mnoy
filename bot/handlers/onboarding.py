"""Onboarding-карусель при первом /start.

Три инлайн-шага «что это», «как искать», «как создавать и анкета»,
плюс закрывающее сообщение с reply-меню. Каждый шаг — `edit_text`
одного и того же сообщения. Юзер может пропустить в любой момент
кнопкой «⏭ Пропустить» — это эквивалент дочитывания до конца.

Состояние «уже прошёл онбординг» хранится в `User.search_prefs`
(JSONB), флаг `onboarded`. Так не нужна отдельная миграция, а одна
точка истины для всех будущих per-user флагов.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_reply
from bot.services.users import mark_onboarded, upsert_telegram_user

router = Router(name="onboarding")


@dataclass(frozen=True)
class _Step:
    text: str


_STEPS: tuple[_Step, ...] = (
    _Step(
        text=(
            "👋 <b>Привет!</b>\n\n"
            "Это бот, чтобы найти, <b>что делать сегодня и с кем</b>.\n\n"
            "Здесь можно:\n"
            "• листать события и заявки от других людей,\n"
            "• присоединяться в один клик,\n"
            "• создавать свои встречи и звать компанию.\n\n"
            "Покажу за минуту, как это устроено."
        ),
    ),
    _Step(
        text=(
            "<b>📍 Найти событие · 🤝 Найти компанию</b>\n\n"
            "В двух разделах меню — лента карточек:\n"
            "• <b>События</b> — что происходит в ближайшие дни.\n"
            "• <b>Заявки</b> — кто-то ищет компанию для своего дела.\n\n"
            "Листай стрелками, фильтруй по тегам. Жми "
            "<b>Иду</b> / <b>Хочу</b> — и ты в списке.\n\n"
            "Перед записью посмотри, кто уже идёт, через "
            "<b>👥 Участники</b>."
        ),
    ),
    _Step(
        text=(
            "<b>➕ Создать активность</b>\n\n"
            "Сам организуй встречу или ищи компанию для своего дела. "
            "Бот проведёт через несколько шагов: название, обложка, "
            "время, место, теги. Опционально — ссылка на чат и "
            "приватный режим (с подтверждением заявок).\n\n"
            "После создания модератор проверит, и активность "
            "появится в ленте.\n\n"
            "<b>👤 Мой профиль</b> — все твои активности в одном месте "
            "плюс анкета. Анкету попросят заполнить, когда впервые "
            "нажмёшь «Иду»."
        ),
    ),
)


def _step_keyboard(idx: int) -> InlineKeyboardMarkup:
    """Клавиатура для шага `idx` (0-индексация). На последнем шаге
    «Дальше» становится «✅ Поехали»."""
    is_last = idx == len(_STEPS) - 1
    next_label = "✅ Поехали" if is_last else "Дальше →"
    next_cb = "ob:done" if is_last else f"ob:{idx + 1}"
    rows = [[InlineKeyboardButton(text=next_label, callback_data=next_cb)]]
    if not is_last:
        rows.append(
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="ob:done")],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ──────────────────────────── public API ────────────────────────────────────


async def start_onboarding(message: Message) -> None:
    """Шлёт первое сообщение онбординга. Зовётся из `cmd_start`,
    когда юзер ещё не онбордился."""
    await message.answer(
        _STEPS[0].text,
        reply_markup=_step_keyboard(0),
        parse_mode=ParseMode.HTML,
    )


# ──────────────────────────── callbacks ─────────────────────────────────────


@router.callback_query(F.data == "ob:done")
async def on_done(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    user = await upsert_telegram_user(session, callback.from_user)
    await mark_onboarded(session, user=user)

    # Снимаем inline-клавиатуру с последнего шага и отдельно шлём
    # closing-сообщение с reply-меню — в одном сообщении нельзя
    # одновременно держать inline и reply клавиатуры.
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        "Готово 🎉 Меню снизу — выбирай раздел и поехали.",
        reply_markup=main_menu_reply(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ob:"))
async def on_step(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer()
        return
    try:
        idx = int(callback.data.split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer()
        return
    if idx < 0 or idx >= len(_STEPS):
        await callback.answer()
        return
    try:
        await callback.message.edit_text(
            _STEPS[idx].text,
            reply_markup=_step_keyboard(idx),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
    await callback.answer()
