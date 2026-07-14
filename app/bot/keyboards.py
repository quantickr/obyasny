from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти помощь"), KeyboardButton(text="🤝 Пары")],
            [KeyboardButton(text="📥 Заявки"), KeyboardButton(text="🍫 Баланс")],
            [KeyboardButton(text="👤 Профиль")],
        ],
        resize_keyboard=True,
    )


def request_actions(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Принять", callback_data=f"req_accept:{request_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"req_decline:{request_id}"
                ),
            ]
        ]
    )


def teacher_actions(teacher_id: int, topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🍫 Заявка (шоколадки)",
                    callback_data=f"ask:{teacher_id}:{topic_id}",
                )
            ]
        ]
    )


def open_chat_button(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Открыть чат", callback_data=f"chat_open:{chat_id}"
                )
            ]
        ]
    )
