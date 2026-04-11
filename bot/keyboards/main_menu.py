from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_FIND_EVENTS = "📍 Найти событие"
BTN_FIND_COMPANY = "🤝 Найти компанию"
BTN_CREATE_EVENT = "➕ Создать событие"
BTN_MY_PROFILE = "👤 Мой профиль"


def main_menu_reply() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_FIND_EVENTS)],
            [
                KeyboardButton(text=BTN_FIND_COMPANY),
                KeyboardButton(text=BTN_CREATE_EVENT),
            ],
            [KeyboardButton(text=BTN_MY_PROFILE)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Меню внизу экрана",
    )
