import logging

from aiogram import Bot

logger = logging.getLogger(__name__)


async def notify(bot: Bot, telegram_id: int | None, text: str, **kwargs) -> None:
    """Безопасная отправка уведомления (игнорирует ошибки доставки)."""
    if not telegram_id:
        return
    try:
        await bot.send_message(telegram_id, text, **kwargs)
    except Exception as e:
        logger.warning("Не удалось отправить уведомление %s: %s", telegram_id, e)
