from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти помощь"), KeyboardButton(text="📥 Заявки")],
            [KeyboardButton(text="💬 Чаты"), KeyboardButton(text="🍫 Баланс")],
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


def decline_block_actions(request_id: int) -> InlineKeyboardMarkup:
    """Выбор срока блокировки повторных заявок при отклонении."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Без блока",
                    callback_data=f"req_block:{request_id}:none",
                ),
                InlineKeyboardButton(
                    text="День", callback_data=f"req_block:{request_id}:day"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Неделя", callback_data=f"req_block:{request_id}:week"
                ),
                InlineKeyboardButton(
                    text="Месяц", callback_data=f"req_block:{request_id}:month"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Навсегда",
                    callback_data=f"req_block:{request_id}:forever",
                ),
            ],
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
                ),
                InlineKeyboardButton(
                    text="📜 История",
                    callback_data=f"chat_history:{chat_id}",
                ),
            ]
        ]
    )


def chats_inbox(rows: list[tuple[int, str, str, int]]) -> InlineKeyboardMarkup:
    """Список чатов инбокса. rows: (chat_id, имя, тема/контекст, непрочитано)."""
    keyboard = []
    for chat_id, name, topic, unread in rows:
        badge = f" ({unread})" if unread else ""
        topic_part = f" · {topic}" if topic else ""
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{name}{topic_part}{badge}",
                    callback_data=f"chat_inbox:{chat_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
