from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import main_menu
from app.services import linking_service, user_service

router = Router()


@router.message(CommandStart(deep_link=True))
async def start_with_code(
    message: Message, command: CommandObject, session: AsyncSession
):
    """Deep-link /start <code> — привязка Telegram к веб-аккаунту."""
    code = command.args
    user_id = await linking_service.consume_link_code(code) if code else None

    tg = message.from_user
    if user_id is not None:
        try:
            _, merged = await user_service.link_or_merge_telegram(
                session, user_id, tg.id, tg.username
            )
            text = (
                "✅ Аккаунты объединены! Твои темы и прогресс из бота "
                "перенесены на сайт."
                if merged
                else "✅ Аккаунт привязан! Теперь бот и сайт работают вместе."
            )
            await message.answer(text, reply_markup=main_menu())
            return
        except user_service.AuthError as e:
            # Откатываем полусостояние, иначе middleware закоммитит его.
            await session.rollback()
            await message.answer(f"⚠️ {e}")

    # Код невалиден/просрочен — обычный старт.
    await _ensure_user(message, session)


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession):
    await _ensure_user(message, session)


async def _ensure_user(message: Message, session: AsyncSession) -> None:
    tg = message.from_user
    await user_service.get_or_create_telegram_user(
        session,
        telegram_id=tg.id,
        telegram_username=tg.username,
        display_name=tg.full_name,
    )
    await message.answer(
        "🎓 Привет! Это «Объясни!» — платформа взаимопомощи студентов.\n\n"
        "Найди, кто объяснит тебе тему, а взамен объясни свою или отблагодари "
        "шоколадками 🍫.\n\nВыбери действие ниже:",
        reply_markup=main_menu(),
    )
