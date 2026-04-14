from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from bot.constants import ACTIVITY_EVENT, ACTIVITY_PUBLISHED, ACTIVITY_SEEKING
from bot.handlers.onboarding import start_onboarding
from bot.keyboards.activity_feed import format_activity_card_text
from bot.keyboards.main_menu import main_menu_reply
from bot.models import EventTemplate
from bot.services.activities import (
    count_joined_members,
    get_activity,
    get_creator_summary,
)
from bot.services.users import (
    is_onboarded,
    mark_onboarded,
    upsert_user_from_message,
)

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    user = await upsert_user_from_message(session, message)
    args = (command.args or "").strip()

    # Канонический формат ссылки после унификации.
    if args.startswith("act_"):
        try:
            activity_id = int(args.removeprefix("act_").strip())
        except ValueError:
            await message.answer(
                "Не понял ссылку. Открываю меню.", reply_markup=main_menu_reply(),
            )
            await mark_onboarded(session, user=user)
            return
        activity = await get_activity(session, activity_id)
        if activity is None or activity.status != ACTIVITY_PUBLISHED:
            await message.answer(
                "Уже недоступно. Загляни в ленту.",
                reply_markup=main_menu_reply(),
            )
            await mark_onboarded(session, user=user)
            return
        members = await count_joined_members(session, activity_id)
        author_name = author_age = None
        if activity.kind == ACTIVITY_SEEKING:
            author_name, author_age = await get_creator_summary(session, activity)
        text = format_activity_card_text(
            activity,
            members=members,
            author_name=author_name,
            author_age=author_age,
        )
        section = (
            "📍 Найти событие" if activity.kind == ACTIVITY_EVENT else "🤝 Найти компанию"
        )
        await message.answer(
            text + f"\n\nОткрой раздел «{section}» и нажми «Иду» / «Хочу», чтобы записаться.",
            reply_markup=main_menu_reply(),
        )
        # Юзер пришёл по конкретной ссылке — не нужно ему туристического
        # тура по боту, считаем что онбординг пройден.
        await mark_onboarded(session, user=user)
        return

    # Deep link из канала: шаблон события.
    if args.startswith("tpl_"):
        try:
            tpl_id = int(args.removeprefix("tpl_").strip())
        except ValueError:
            await message.answer("Не понял ссылку. Открываю меню.", reply_markup=main_menu_reply())
            await mark_onboarded(session, user=user)
            return
        template = await session.get(EventTemplate, tpl_id)
        if template is None:
            await message.answer("Шаблон не найден.", reply_markup=main_menu_reply())
            await mark_onboarded(session, user=user)
            return

        # Ищем активные события по этому шаблону
        from sqlalchemy import select
        from bot.models import Activity
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Activity)
            .where(Activity.template_id == tpl_id)
            .where(Activity.status == ACTIVITY_PUBLISHED)
            .where(Activity.expires_at >= now)
            .order_by(Activity.starts_at.asc())
            .limit(5),
        )
        existing = list(result.scalars().all())

        if existing:
            from bot.utils.formatting import esc as esc_html, format_datetime_msk
            from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
            text = f"<b>{esc_html(template.title)}</b>\n\nУже есть события — присоединяйся или создай своё:\n"
            rows = []
            for act in existing:
                members_cnt = await count_joined_members(session, act.id)
                when = format_datetime_msk(act.starts_at) if act.starts_at else ""
                label = f"🎉 {when} ({members_cnt} чел.)"
                rows.append([InlineKeyboardButton(
                    text=label[:60],
                    callback_data=f"tpl:act:{act.id}",
                )])
            rows.append([InlineKeyboardButton(
                text="➕ Создать своё",
                callback_data=f"tpl:new:{tpl_id}",
            )])
            await message.answer(
                text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
                parse_mode="HTML",
            )
        else:
            from bot.handlers.activity_create import start_create_from_template
            await start_create_from_template(message, state, template)

        await mark_onboarded(session, user=user)
        return

    # Старые форматы из уже опубликованных постов канала: id'ы старых
    # таблиц после миграции 007 не сохранились, поэтому честно говорим
    # «устарело».
    if args.startswith("event_") or args.startswith("seek_"):
        await message.answer(
            "Ссылка из старых постов устарела. Открой раздел в меню — там актуальная лента.",
            reply_markup=main_menu_reply(),
        )
        await mark_onboarded(session, user=user)
        return

    # Голый /start. Если юзер ещё не видел онбординг — показываем,
    # иначе обычное приветствие с меню.
    if not is_onboarded(user):
        await start_onboarding(message)
        return

    await message.answer(
        "Привет! Выбери действие в меню ниже — до встречи пара кликов.",
        reply_markup=main_menu_reply(),
    )


@router.callback_query(F.data.startswith("tpl:act:"))
async def on_tpl_join_existing(
    callback: CallbackQuery, session: AsyncSession,
) -> None:
    """Юзер выбрал существующее событие из шаблона."""
    if callback.message is None or callback.from_user is None:
        await callback.answer()
        return
    try:
        activity_id = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    activity = await get_activity(session, activity_id)
    if activity is None or activity.status != ACTIVITY_PUBLISHED:
        await callback.answer("Уже недоступно.", show_alert=True)
        return
    members = await count_joined_members(session, activity_id)
    text = format_activity_card_text(
        activity, members=members,
    )
    section = "📍 Найти событие" if activity.kind == ACTIVITY_EVENT else "🤝 Найти компанию"
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        text + f"\n\nОткрой раздел «{section}» и нажми «Иду», чтобы записаться.",
        reply_markup=main_menu_reply(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tpl:new:"))
async def on_tpl_create_new(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext,
) -> None:
    """Юзер хочет создать своё событие по шаблону."""
    if callback.message is None:
        await callback.answer()
        return
    try:
        tpl_id = int(callback.data.split(":", 2)[2])
    except (IndexError, ValueError):
        await callback.answer()
        return
    template = await session.get(EventTemplate, tpl_id)
    if template is None:
        await callback.answer("Шаблон не найден.", show_alert=True)
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    from bot.handlers.activity_create import start_create_from_template
    await start_create_from_template(callback.message, state, template)
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Команды: /start — меню и ссылки из канала, /help — эта справка, "
        "/cancel — отменить создание.",
    )
