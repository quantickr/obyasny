from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import chats_inbox, open_chat_button
from app.bot.states import ChatStates
from app.core.database import async_session_factory
from app.events import bus
from app.events.schemas import ChatEvent
from app.models.chat import Chat, MessageSource
from app.services import chat_service, user_service

router = Router()

_CTX_RU = {
    "request": "по заявке",
    "listing": "по объявлению",
    "match": "подбор пары",
    "direct": "личный чат",
}


@router.message(Command("stop"), ChatStates.active)
async def stop_chat(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вышли из чата.")


@router.message(F.text == "💬 Чаты")
async def show_chats(message: Message, session: AsyncSession):
    """Инбокс: список чатов с непрочитанными (имя + тема + счётчик)."""
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        await message.answer("Сначала /start")
        return
    chats = await chat_service.list_user_chats(session, me.id)
    if not chats:
        await message.answer("У вас пока нет чатов.")
        return
    unread = await chat_service.unread_by_chat(session, me.id)
    rows = []
    for c in chats:
        partner_id = chat_service.other_participant(c, me.id)
        partner = await user_service.get_by_id(session, partner_id)
        name = partner.display_name if partner else "Собеседник"
        # Для чатов из заявки title = «Тема — Имя отправителя»: берём тему.
        if c.title:
            topic = c.title.split(" — ")[0]
        elif c.context_type:
            topic = _CTX_RU.get(c.context_type.value, "")
        else:
            topic = ""
        rows.append((c.id, name, topic, unread.get(c.id, 0)))
    total = sum(r[3] for r in rows)
    header = (
        f"💬 Ваши чаты (непрочитанных: {total}):"
        if total
        else "💬 Ваши чаты:"
    )
    await message.answer(header, reply_markup=chats_inbox(rows))


@router.callback_query(F.data.startswith("chat_inbox:"))
async def open_inbox_chat(callback: CallbackQuery, session: AsyncSession):
    """Показывает непрочитанные сообщения выбранного чата и помечает прочитанными."""
    chat_id = int(callback.data.split(":")[1])
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    chat = await chat_service.get_chat_for_user(session, chat_id, me.id)
    if chat is None:
        await callback.answer("Чат не найден", show_alert=True)
        return
    partner_id = chat_service.other_participant(chat, me.id)
    partner = await user_service.get_by_id(session, partner_id)
    name = partner.display_name if partner else "Собеседник"

    unread = await chat_service.unread_messages(session, chat_id, me.id)
    if unread:
        lines = "\n".join(f"• {m.body}" for m in unread)
        text = f"💬 Непрочитанные от {name}:\n{lines}"
        await chat_service.mark_chat_read(session, chat_id, me.id)
        await session.commit()
    else:
        text = f"💬 Чат с {name}. Новых сообщений нет."
    await callback.answer()
    await callback.message.answer(text, reply_markup=open_chat_button(chat_id))


@router.callback_query(F.data.startswith("chat_history:"))
async def show_history(callback: CallbackQuery, session: AsyncSession):
    """Показывает последние 10 сообщений чата (история переписки)."""
    chat_id = int(callback.data.split(":")[1])
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    chat = await chat_service.get_chat_for_user(session, chat_id, me.id)
    if chat is None:
        await callback.answer("Чат не найден", show_alert=True)
        return

    messages = await chat_service.get_messages(session, chat_id)
    await callback.answer()
    if not messages:
        await callback.message.answer("💬 История пуста.")
        return

    partner_id = chat_service.other_participant(chat, me.id)
    partner = await user_service.get_by_id(session, partner_id)
    partner_name = partner.display_name if partner else "Собеседник"

    lines = []
    for m in messages[-10:]:
        who = "Вы" if m.sender_id == me.id else partner_name
        lines.append(f"{who}: {m.body}")
    text = "📜 Последние сообщения:\n\n" + "\n".join(lines)
    await callback.message.answer(text)


async def _relay_to_web(
    message: Message,
    session: AsyncSession,
    sender_id: int,
    chat_id: int,
    reply_to_id: int | None,
    reply_preview: str | None,
) -> None:
    """Сохраняет сообщение из Telegram и публикует в шину (дойдёт на сайт)."""
    msg = await chat_service.save_message(
        session,
        chat_id=chat_id,
        sender_id=sender_id,
        body=message.text,
        source=MessageSource.telegram,
        tg_message_id=message.message_id,
        reply_to_id=reply_to_id,
    )
    # Снимаем поля до commit: после него объект может быть expired.
    # body берём из msg — это цензурированная версия из save_message.
    msg_id = msg.id
    clean_body = msg.body
    created_at = msg.created_at.isoformat()
    await session.commit()

    event = ChatEvent(
        chat_id=chat_id,
        message_id=msg_id,
        sender_id=sender_id,
        body=clean_body,
        source="telegram",
        tg_message_id=message.message_id,
        reply_to_id=reply_to_id,
        reply_preview=reply_preview,
        created_at=created_at,
    )
    await bus.publish_message(event)


@router.message(ChatStates.active, F.text)
async def relay_from_telegram(
    message: Message, state: FSMContext, session: AsyncSession
):
    """Сообщение из Telegram в режиме активного чата → пересылаем на сайт."""
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

    # Reply в Telegram → находим цитируемое сообщение чата по его tg_message_id.
    reply_to_id: int | None = None
    reply_preview: str | None = None
    if message.reply_to_message is not None:
        original = await chat_service.find_message_by_tg_id(
            session, chat_id, message.reply_to_message.message_id
        )
        if original is not None:
            reply_to_id = original.id
            reply_preview = original.body[:120]

    await _relay_to_web(
        message, session, me.id, chat_id, reply_to_id, reply_preview
    )


@router.message(F.reply_to_message, F.text)
async def relay_reply_out_of_chat(message: Message, session: AsyncSession):
    """Reply в Telegram на доставленное ботом сообщение — вне режима чата.

    Позволяет отвечать собеседнику, просто сделав reply на уведомление
    «💬 Имя: текст», без нажатия кнопки «Открыть чат».
    """
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        return

    original = await chat_service.find_message_by_tg_id_for_user(
        session, me.id, message.reply_to_message.message_id
    )
    if original is None:
        return  # reply не на сообщение чата — не наш случай

    await _relay_to_web(
        message,
        session,
        me.id,
        original.chat_id,
        reply_to_id=original.id,
        reply_preview=original.body[:120],
    )


async def chat_relay_subscriber(bot) -> None:
    """Фоновая задача бота: слушает ВСЕ чаты. Текст web-сообщений сразу в Telegram
    НЕ пересылается — получателю копятся непрочитанные, а он один раз получает
    лёгкое уведомление о новом сообщении и открывает «💬 Чаты»."""
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
        if not (recipient and recipient.telegram_id):
            continue
        # Получатель прямо сейчас смотрит этот чат на сайте — не беспокоим в TG.
        if await bus.is_present(event.chat_id, recipient_id):
            continue
        # Уведомляем на КАЖДОЕ новое сообщение, без раскрытия текста.
        name = sender.display_name if sender else "Собеседник"
        try:
            await bot.send_message(
                recipient.telegram_id,
                f"💬 Новое сообщение от {name}.\n"
                "Откройте «💬 Чаты», чтобы прочитать.",
                reply_markup=open_chat_button(event.chat_id),
            )
        except Exception:
            continue
