from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import ChatStates
from app.core.database import async_session_factory
from app.events import bus
from app.events.schemas import ChatEvent
from app.models.chat import Chat, MessageSource
from app.services import chat_service, user_service

router = Router()


@router.message(Command("stop"), ChatStates.active)
async def stop_chat(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вышли из чата.")


@router.message(ChatStates.active, F.text)
async def relay_from_telegram(
    message: Message, state: FSMContext, session: AsyncSession
):
    """Сообщение из Telegram → сохраняем и публикуем в шину (дойдёт на сайт)."""
    data = await state.get_data()
    chat_id = data.get("chat_id")
    if not chat_id:
        await state.clear()
        return

    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        return

    chat = await chat_service.get_chat_for_user(session, chat_id, me.id)
    if chat is None:
        await state.clear()
        return

    msg = await chat_service.save_message(
        session,
        chat_id=chat_id,
        sender_id=me.id,
        body=message.text,
        source=MessageSource.telegram,
        tg_message_id=message.message_id,
    )
    await session.commit()

    event = ChatEvent(
        chat_id=chat_id,
        message_id=msg.id,
        sender_id=me.id,
        body=message.text,
        source="telegram",
        tg_message_id=message.message_id,
        created_at=msg.created_at.isoformat(),
    )
    await bus.publish_message(event)


async def chat_relay_subscriber(bot) -> None:
    """Фоновая задача бота: слушает ВСЕ чаты и доставляет в Telegram сообщения,
    пришедшие НЕ из Telegram (source='web'), второму участнику."""
    async for event in bus.subscribe_all():
        if event.source == "telegram":
            continue  # не эхо-им обратно то, что пришло из TG
        async with async_session_factory() as session:
            chat = await session.get(Chat, event.chat_id)
            if chat is None:
                continue
            recipient_id = (
                chat.user2_id
                if chat.user1_id == event.sender_id
                else chat.user1_id
            )
            recipient = await user_service.get_by_id(session, recipient_id)
            sender = await user_service.get_by_id(session, event.sender_id)
        if recipient and recipient.telegram_id:
            name = sender.display_name if sender else "Собеседник"
            try:
                await bot.send_message(
                    recipient.telegram_id, f"💬 {name}: {event.body}"
                )
            except Exception:
                pass
