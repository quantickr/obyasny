import asyncio
import logging
import socket

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand

from app.bot.handlers import chat, misc, requests, search, start
from app.bot.middlewares import DbSessionMiddleware
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)


def build_ipv4_session() -> AiohttpSession:
    """Сессия бота, форсированная на IPv4.

    Timeweb публикует IPv6-маршрут (DNS отдаёт AAAA для api.telegram.org),
    но реально его не маршрутизирует: happy-eyeballs зависает на коннекте
    по IPv6, и запросы к Telegram уходят в таймаут (TelegramNetworkError).
    Добавляем family=AF_INET в параметры TCPConnector, чтобы ходить только
    по IPv4.
    """
    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    return session


def build_dispatcher() -> Dispatcher:
    # FSM-состояния храним в Redis, чтобы переживать рестарты бота.
    storage = RedisStorage(redis=redis_client)
    dp = Dispatcher(storage=storage)

    session_mw = DbSessionMiddleware()
    dp.message.middleware(session_mw)
    dp.callback_query.middleware(session_mw)

    # Порядок важен: специфичные состояния (chat) раньше общих меню.
    dp.include_router(start.router)
    dp.include_router(chat.router)
    dp.include_router(requests.router)
    dp.include_router(search.router)
    dp.include_router(misc.router)
    return dp


async def main() -> None:
    setup_logging()
    if not settings.bot_token or settings.bot_token.startswith("123456:"):
        logger.error("BOT_TOKEN не задан. Укажите токен от @BotFather в .env")
        return

    bot = Bot(token=settings.bot_token, session=build_ipv4_session())
    dp = build_dispatcher()

    # Меню команд Telegram (синяя кнопка «/»).
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запуск / привязка аккаунта"),
            BotCommand(command="menu", description="Показать меню (кнопки)"),
        ]
    )

    # Фоновая задача: доставка web-сообщений в Telegram через Redis Pub/Sub.
    relay_task = asyncio.create_task(chat.chat_relay_subscriber(bot))

    logger.info("Бот запускается (long polling)...")
    try:
        await dp.start_polling(bot)
    finally:
        relay_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
