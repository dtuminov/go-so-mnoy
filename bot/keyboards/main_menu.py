from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_FIND_EVENTS = "📍 Найти событие"
BTN_FIND_COMPANY = "🤝 Найти компанию"
BTN_CREATE_ACTIVITY = "➕ Создать активность"
BTN_MY_PROFILE = "👤 Мой профиль"
BTN_CANCEL = "❌ Отменить"


def main_menu_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_FIND_EVENTS),
                KeyboardButton(text=BTN_FIND_COMPANY),
            ],
            [KeyboardButton(text=BTN_CREATE_ACTIVITY)],
            [KeyboardButton(text=BTN_MY_PROFILE)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Меню внизу экрана",
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с одной кнопкой «Отменить» — показывается во время FSM."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        input_field_placeholder="Нажми «Отменить» чтобы выйти",
    )
