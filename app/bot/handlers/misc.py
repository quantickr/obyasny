from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import open_chat_button
from app.bot.notifier import notify
from app.core.config import settings
from app.models.chat import ChatContext
from app.services import (
    chat_service,
    chocolate_service,
    match_service,
    user_service,
)

router = Router()


@router.message(F.text == "🍫 Баланс")
async def balance(message: Message, session: AsyncSession):
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        await message.answer("Сначала /start")
        return
    bal = await chocolate_service.get_balance(session, me.id)
    await message.answer(f"🍫 Ваш баланс шоколадок: {bal}")


@router.message(F.text == "👤 Профиль")
async def profile(message: Message, session: AsyncSession):
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        await message.answer("Сначала /start")
        return
    linked = "✅ привязан к сайту" if me.email else "не привязан к email"
    await message.answer(
        f"👤 {me.display_name}\n🍫 Баланс: {me.chocolate_balance}\n"
        f"Аккаунт: {linked}\n\n"
        f"Управлять темами удобнее на сайте: {settings.webapp_base_url}/profile"
    )


@router.message(F.text == "🤝 Пары")
async def matches(message: Message, session: AsyncSession):
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        await message.answer("Сначала /start")
        return
    candidates = await match_service.find_mutual_matches(session, me.id, limit=5)
    if not candidates:
        await message.answer(
            "Пока нет взаимовыгодных пар. Добавьте больше тем в профиль на сайте."
        )
        return
    for c in candidates:
        await message.answer(
            f"🤝 {c.partner.display_name}\n"
            f"Вы объясните: {c.i_teach_topic.name}\n"
            f"Партнёр объяснит: {c.partner_teaches_topic.name}",
            reply_markup=_connect_button(c.partner.id),
        )


def _connect_button(partner_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Связаться", callback_data=f"match_connect:{partner_id}"
                )
            ]
        ]
    )


@router.callback_query(F.data.startswith("match_connect:"))
async def connect_match(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    partner_id = int(callback.data.split(":")[1])
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    chat = await chat_service.get_or_create_chat(
        session, me.id, partner_id, context_type=ChatContext.match
    )
    await session.commit()

    partner = await user_service.get_by_id(session, partner_id)
    if partner and partner.telegram_id:
        await notify(
            callback.bot,
            partner.telegram_id,
            f"🤝 {me.display_name} хочет обменяться знаниями с вами!",
            reply_markup=open_chat_button(chat.id),
        )
    await callback.answer("Чат создан!")
    await callback.message.answer(
        "💬 Чат готов. Нажмите «Открыть чат», чтобы начать переписку.",
        reply_markup=open_chat_button(chat.id),
    )
