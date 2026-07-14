from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import teacher_actions
from app.bot.states import SearchStates
from app.models.request import OfferType
from app.services import request_service, search_service, user_service

router = Router()


@router.message(F.text == "🔍 Найти помощь")
async def ask_topic(message: Message, state: FSMContext):
    await state.set_state(SearchStates.waiting_topic)
    await message.answer("Введите тему, по которой нужна помощь:")


@router.message(SearchStates.waiting_topic)
async def do_search(message: Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    me = await user_service.get_by_telegram_id(session, message.from_user.id)
    if me is None:
        await message.answer("Сначала нажмите /start")
        return

    results = await search_service.find_teachers_by_query(
        session, message.text, exclude_user_id=me.id, limit=10
    )
    if not results:
        await message.answer("Никого не нашлось по этой теме 😕")
        return

    await message.answer(f"Нашлось {len(results)} чел.:")
    for teacher, topic in results:
        text = f"👤 {teacher.display_name}\nОбъяснит: {topic.name}"
        await message.answer(text, reply_markup=teacher_actions(teacher.id, topic.id))


@router.callback_query(F.data.startswith("ask:"))
async def send_request(callback: CallbackQuery, session: AsyncSession):
    _, teacher_id, topic_id = callback.data.split(":")
    me = await user_service.get_by_telegram_id(session, callback.from_user.id)
    if me is None:
        await callback.answer("Сначала /start", show_alert=True)
        return
    try:
        req = await request_service.create_request(
            session,
            sender_id=me.id,
            receiver_id=int(teacher_id),
            topic_id=int(topic_id),
            offer_type=OfferType.chocolates,
        )
        await session.commit()
        await callback.answer("Заявка отправлена! 🍫")
        await callback.message.edit_reply_markup(reply_markup=None)

        # Уведомляем преподавателя, если у него есть Telegram.
        from app.bot.keyboards import request_actions
        from app.bot.notifier import notify

        teacher = await user_service.get_by_id(session, int(teacher_id))
        if teacher and teacher.telegram_id:
            await notify(
                callback.bot,
                teacher.telegram_id,
                f"📥 Новая заявка от {me.display_name} — просят объяснить тему.",
                reply_markup=request_actions(req.id),
            )
    except request_service.RequestError as e:
        await callback.answer(str(e), show_alert=True)
