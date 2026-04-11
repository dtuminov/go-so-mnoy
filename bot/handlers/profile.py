from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import ACTIVITY_EVENT, ACTIVITY_PUBLISHED
from bot.keyboards.main_menu import main_menu_reply
from bot.services.activities import get_activity, join_activity
from bot.services.users import update_user_profile, upsert_user_from_message
from bot.utils.formatting import esc

router = Router(name="profile")

PENDING_ACTIVITY_KEY = "pending_join_activity_id"
CB_EDIT_PROFILE = "profile:edit"


class ProfileSG(StatesGroup):
    avatar = State()
    age = State()
    bio = State()


def _welcome_text(*, activity_title: str | None, editing: bool = False) -> str:
    if editing:
        prefix = "Обновляем анкету.\n\n"
    elif activity_title:
        prefix = f"«{esc(activity_title)}» — после анкеты подадим заявку автоматически.\n\n"
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
    pending_event_id: int | None = None,
    pending_seeking_id: int | None = None,  # backward-compat для существующих хэндлеров
    activity_title: str | None = None,
    editing: bool = False,
) -> None:
    """Стартует FSM анкеты.

    Параметры `pending_event_id` / `pending_seeking_id` оставлены ради
    обратной совместимости с прежним API; внутри они мерджатся в общий
    `pending_join_activity_id`.
    """
    await state.clear()
    await state.set_state(ProfileSG.avatar)
    data: dict = {"editing": editing}
    pending = pending_event_id if pending_event_id is not None else pending_seeking_id
    if pending is not None:
        data[PENDING_ACTIVITY_KEY] = pending
    await state.update_data(data)
    await target_message.answer(
        _welcome_text(activity_title=activity_title, editing=editing),
        parse_mode=ParseMode.HTML,
    )


# ── edit callback (из карточки профиля) ──────────────────────────────────────


@router.callback_query(F.data == CB_EDIT_PROFILE, StateFilter(default_state))
async def on_edit_profile_cb(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        await callback.answer()
        return
    await callback.answer()
    await begin_profile_flow(callback.message, state, editing=True)


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
    await message.answer(
        "Сейчас нужно именно <b>фото</b>. Отправь одно изображение.",
        parse_mode=ParseMode.HTML,
    )


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

    pending = data.get(PENDING_ACTIVITY_KEY)
    editing = data.get("editing", False)
    await state.clear()

    if editing:
        await message.answer("Профиль обновлён.", reply_markup=main_menu_reply())
        return

    text = "Готово — профиль сохранён. Дальше запись в один клик."

    # Авто-вступление в активность, на которую кликали до анкеты.
    if pending is not None:
        try:
            aid = int(pending)
        except (TypeError, ValueError):
            aid = None
        if aid is not None:
            activity = await get_activity(session, aid)
            if activity is not None and activity.status == ACTIVITY_PUBLISHED:
                _, action = await join_activity(
                    session, activity=activity, user_id=user.id,
                )
                if action == "created_joined":
                    if activity.kind == ACTIVITY_EVENT:
                        text += f"\n\n✅ Ты в списке участников «{esc(activity.title)}»."
                    else:
                        text += f"\n\n✅ Отклик на заявку «{esc(activity.title)}» отправлен автору."
                elif action == "created_pending":
                    text += (
                        f"\n\n⏳ Заявка на «{esc(activity.title)}» отправлена. "
                        "Ждём подтверждения организатора."
                    )
                else:  # already
                    text += "\n\nТы уже в списке — всё ок."
            else:
                text += "\n\nЭто уже недоступно — выбери другое."

    await message.answer(text, reply_markup=main_menu_reply())
