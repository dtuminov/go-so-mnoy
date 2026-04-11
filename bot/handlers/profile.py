from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import EVENT_PUBLISHED, SEEKING_PUBLISHED
from bot.keyboards.main_menu import main_menu_reply
from bot.services.company_seeking import get_seeking, user_responded
from bot.services.events import get_event, user_joined_event
from bot.services.users import update_user_profile, upsert_user_from_message
from bot.utils.formatting import esc

router = Router(name="profile")

PENDING_JOIN_KEY = "pending_join_event_id"
PENDING_SEEK_KEY = "pending_seek_id"
CB_EDIT_PROFILE = "profile:edit"


class ProfileSG(StatesGroup):
    avatar = State()
    age = State()
    bio = State()


def _welcome_text(*, event_title: str | None, editing: bool = False) -> str:
    if editing:
        prefix = "Обновляем анкету.\n\n"
    elif event_title:
        prefix = f"Событие «{esc(event_title)}» — после анкеты запишем автоматически.\n\n"
    else:
        prefix = "Чтобы участвовать во встречах, заполни <b>анкету</b>.\n\n"
    return (
        prefix
        + "<b>Шаг 1/3</b>: отправь <b>одно фото</b> (как картинку, не файлом).\n"
        "Отмена: /cancel"
    )


async def begin_profile_flow(
    target_message: Message,
    state: FSMContext,
    *,
    pending_event_id: int | None,
    pending_seeking_id: int | None = None,
    event_title: str | None = None,
    editing: bool = False,
) -> None:
    await state.clear()
    await state.set_state(ProfileSG.avatar)
    data: dict = {"editing": editing}
    if pending_event_id is not None:
        data[PENDING_JOIN_KEY] = pending_event_id
    if pending_seeking_id is not None:
        data[PENDING_SEEK_KEY] = pending_seeking_id
    await state.update_data(data)
    await target_message.answer(
        _welcome_text(event_title=event_title, editing=editing),
        parse_mode=ParseMode.HTML,
    )


# ── edit callback (из карточки профиля) ──────────────────────────────────────

@router.callback_query(F.data == CB_EDIT_PROFILE, StateFilter(default_state))
async def on_edit_profile_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    await begin_profile_flow(callback.message, state, pending_event_id=None, editing=True)


# ── /cancel внутри анкеты ────────────────────────────────────────────────────

@router.message(Command("cancel"), StateFilter(ProfileSG))
async def profile_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    editing = data.get("editing", False)
    await state.clear()
    if editing:
        text = "Редактирование отменено — старые данные сохранены."
    else:
        text = "Анкета отменена. Когда будешь готов — снова нажми «Иду ✅»."
    await message.answer(text, reply_markup=main_menu_reply())


# ── шаги FSM ─────────────────────────────────────────────────────────────────

@router.message(ProfileSG.avatar, F.photo)
async def profile_avatar(message: Message, state: FSMContext) -> None:
    photos = message.photo
    if not photos:
        await message.answer("Пришли одно фото.")
        return
    await state.update_data(avatar_file_id=photos[-1].file_id)
    await state.set_state(ProfileSG.age)
    await message.answer(
        "Шаг 2/3: напиши свой <b>возраст</b> одним числом (например, 24).",
        parse_mode=ParseMode.HTML,
    )


@router.message(ProfileSG.avatar)
async def profile_avatar_wrong(message: Message) -> None:
    await message.answer("Сейчас нужно именно <b>фото</b>. Отправь одно изображение.", parse_mode=ParseMode.HTML)


@router.message(ProfileSG.age, F.text)
async def profile_age(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        age = int(raw)
    except ValueError:
        await message.answer("Напиши возраст числом, например: 22")
        return
    if age < 14 or age > 99:
        await message.answer("Укажи возраст от 14 до 99.")
        return
    await state.update_data(age=age)
    await state.set_state(ProfileSG.bio)
    await message.answer(
        "Шаг 3/3: <b>о себе</b> — от 10 символов: чем занимаешься, что любишь.",
        parse_mode=ParseMode.HTML,
    )


@router.message(ProfileSG.age)
async def profile_age_wrong(message: Message) -> None:
    await message.answer("Отправь возраст одним числом.")


@router.message(ProfileSG.bio, F.text)
async def profile_bio_finish(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    bio = (message.text or "").strip()
    if len(bio) < 10:
        await message.answer("Минимум 10 символов — чуть подробнее.")
        return
    if len(bio) > 2000:
        bio = bio[:2000]

    data = await state.get_data()
    avatar = data.get("avatar_file_id")
    age = data.get("age")
    if not avatar or age is None:
        await state.clear()
        await message.answer(
            "Данные анкеты потерялись. Начни снова.",
            reply_markup=main_menu_reply(),
        )
        return

    user = await upsert_user_from_message(session, message)
    await update_user_profile(
        session,
        user_id=user.id,
        avatar_file_id=str(avatar),
        age=int(age),
        bio=bio,
    )

    pending = data.get(PENDING_JOIN_KEY)
    editing = data.get("editing", False)
    await state.clear()

    if editing:
        await message.answer("Профиль обновлён.", reply_markup=main_menu_reply())
        return

    text = "Готово — профиль сохранён. Дальше запись на события в один клик."

    # авто-запись на событие
    pending_event = data.get(PENDING_JOIN_KEY)
    if pending_event is not None:
        try:
            eid = int(pending_event)
        except (TypeError, ValueError):
            eid = None
        if eid is not None:
            event = await get_event(session, eid)
            if event is not None and event.status == EVENT_PUBLISHED:
                joined = await user_joined_event(session, event_id=eid, user_id=user.id)
                if joined:
                    text += f"\n\n✅ Ты в списке участников «{esc(event.title)}»."
                else:
                    text += "\n\nПо этому событию ты уже в списке — всё ок."
            else:
                text += "\n\nЭто событие уже недоступно — выбери другое в ленте."

    # авто-отклик на заявку «найти компанию»
    pending_seek = data.get(PENDING_SEEK_KEY)
    if pending_seek is not None:
        try:
            sid = int(pending_seek)
        except (TypeError, ValueError):
            sid = None
        if sid is not None:
            seeking = await get_seeking(session, sid)
            if seeking is not None and seeking.status == SEEKING_PUBLISHED:
                responded = await user_responded(session, seeking_id=sid, user_id=user.id)
                if responded:
                    text += f"\n\n✅ Отклик на заявку «{esc(seeking.title)}» отправлен автору."
                else:
                    text += "\n\nПо этой заявке ты уже откликнулся — всё ок."
            else:
                text += "\n\nЭта заявка уже недоступна — выбери другую в разделе «🤝 Найти компанию»."

    await message.answer(text, reply_markup=main_menu_reply())
