from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.core.database import async_session_factory


class DbSessionMiddleware(BaseMiddleware):
    """Инъекция async-сессии БД в каждый хендлер через data['session']."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            result = await handler(event, data)
            await session.commit()
            return result
