from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import open_chat_button
from app.bot.notifier import notify
from app.bot.states import ChatStates
from app.services import chat_service, request_service, user_service

router = Router()


@router.message(F.text == "📥 Заявки")
async def show_incoming(message: Message, session: AsyncSession):
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        await message.answer("Сначала /start")
        return
    reqs = await request_service.incoming(session, me.id)
    if not reqs:
        await message.answer("Нет входящих заявок.")
        return
    from app.bot.keyboards import request_actions

    for req in reqs:
        sender_name = req.sender.display_name if req.sender else "Пользователь"
        topic_name = req.topic.name if req.topic else "—"
        text = (
            f"📥 Заявка #{req.id}\n"
            f"От: {sender_name}\n"
            f"Тема: {topic_name}"
        )
        if req.message:
            text += f"\nОписание: {req.message}"
        await message.answer(text, reply_markup=request_actions(req.id))


@router.callback_query(F.data.startswith("req_accept:"))
async def accept(callback: CallbackQuery, session: AsyncSession):
    req_id = int(callback.data.split(":")[1])
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    try:
        req = await request_service.accept_request(session, req_id, me.id)
        await session.commit()
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Принято! 🍫 +1")

        # Уведомляем отправителя о принятии + ссылка на чат.
        sender = await user_service.get_by_id(session, req.sender_id)
        if sender and sender.telegram_id and req.chat_id:
            await notify(
                callback.bot,
                sender.telegram_id,
                f"✅ {me.display_name} принял вашу заявку! Можно начать чат.",
                reply_markup=open_chat_button(req.chat_id),
            )
    except request_service.RequestError as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("req_decline:"))
async def decline(callback: CallbackQuery):
    """Отклонение: показываем выбор срока блокировки повторных заявок."""
    req_id = int(callback.data.split(":")[1])
    from app.bot.keyboards import decline_block_actions

    await callback.answer()
    await callback.message.edit_text(
        "Отклонить заявку. Заблокировать повторные заявки от этого пользователя?",
        reply_markup=decline_block_actions(req_id),
    )


@router.callback_query(F.data.startswith("req_block:"))
async def decline_with_block(callback: CallbackQuery, session: AsyncSession):
    _, req_id_raw, block = callback.data.split(":")
    req_id = int(req_id_raw)
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    try:
        await request_service.decline_request(
            session, req_id, me.id, block=block
        )
        await session.commit()
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отклонено")
    except request_service.RequestError as e:
        await callback.answer(str(e), show_alert=True)


@router.callback_query(F.data.startswith("chat_open:"))
async def open_chat(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
):
    chat_id = int(callback.data.split(":")[1])
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    chat = await chat_service.get_chat_for_user(session, chat_id, me.id)
    if chat is None:
        await callback.answer("Чат не найден", show_alert=True)
        return
    await state.set_state(ChatStates.active)
    await state.update_data(chat_id=chat_id)
    await callback.answer()

    # Показываем накопившиеся непрочитанные и помечаем их прочитанными.
    partner_id = chat_service.other_participant(chat, me.id)
    partner = await user_service.get_by_id(session, partner_id)
    name = partner.display_name if partner else "Собеседник"
    unread = await chat_service.unread_messages(session, chat_id, me.id)
    if unread:
        lines = "\n".join(f"• {m.body}" for m in unread)
        await chat_service.mark_chat_read(session, chat_id, me.id)
        await session.commit()
        await callback.message.answer(f"💬 Непрочитанные от {name}:\n{lines}")

    await callback.message.answer(
        "💬 Вы в чате. Пишите сообщения — они дойдут собеседнику.\n"
        "Команда /stop — выйти из чата."
    )
