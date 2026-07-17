from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import main_menu, register_button
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
    await _require_registered(message, session)


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession):
    await _require_registered(message, session)


async def _require_registered(message: Message, session: AsyncSession) -> None:
    """Пускает в бота только зарегистрированных на сайте (есть аккаунт с этим
    telegram_id). Новый пользователь НЕ создаётся — ему предлагаем регистрацию.
    """
    tg = message.from_user
    me = await user_service.get_by_telegram_id(session, tg.id)
    if me is None:
        await message.answer(
            "👋 Чтобы пользоваться ботом «Объясни!», сначала зарегистрируйтесь "
            "на сайте — это займёт минуту. После регистрации привяжите Telegram "
            "в профиле, и бот заработает.",
            reply_markup=register_button(),
        )
        return
    await message.answer(
        "🎓 Привет! Это «Объясни!» — платформа взаимопомощи студентов.\n\n"
        "Найди, кто объяснит тебе тему, а взамен объясни свою или отблагодари "
        "шоколадками 🍫.\n\nВыбери действие ниже:",
        reply_markup=main_menu(),
    )
