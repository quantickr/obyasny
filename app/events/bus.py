from collections.abc import AsyncGenerator

from app.core.redis_client import redis_client
from app.events.schemas import ChatEvent


def _channel(chat_id: int) -> str:
    return f"chat:{chat_id}"


async def publish_message(event: ChatEvent) -> None:
    await redis_client.publish(_channel(event.chat_id), event.model_dump_json())


async def subscribe_chat(chat_id: int) -> AsyncGenerator[ChatEvent, None]:
    """Подписка на события одного чата (для WebSocket-соединения)."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(_channel(chat_id))
    try:
        async for raw in pubsub.listen():
            if raw is None or raw.get("type") != "message":
                continue
            yield ChatEvent.model_validate_json(raw["data"])
    finally:
        await pubsub.unsubscribe(_channel(chat_id))
        await pubsub.aclose()


async def subscribe_all() -> AsyncGenerator[ChatEvent, None]:
    """Подписка на ВСЕ чаты по шаблону — используется ботом для relay в Telegram."""
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe("chat:*")
    try:
        async for raw in pubsub.listen():
            if raw is None or raw.get("type") != "pmessage":
                continue
            yield ChatEvent.model_validate_json(raw["data"])
    finally:
        await pubsub.punsubscribe("chat:*")
        await pubsub.aclose()


# --- Presence: кто прямо сейчас смотрит открытый чат на сайте ---------------
# Пока у пользователя открыт WebSocket конкретного чата, веб-процесс держит
# ключ presence с коротким TTL и периодически его продлевает. Бот перед
# отправкой уведомления в Telegram проверяет присутствие получателя: если он
# смотрит этот чат на сайте — уведомление не отправляется.

_PRESENCE_TTL = 30  # секунд; веб продлевает чаще, чем истекает


def _presence_key(chat_id: int, user_id: int) -> str:
    return f"presence:chat:{chat_id}:user:{user_id}"


async def mark_present(chat_id: int, user_id: int) -> None:
    """Отмечает, что пользователь смотрит чат (ставит/продлевает ключ с TTL)."""
    await redis_client.set(
        _presence_key(chat_id, user_id), "1", ex=_PRESENCE_TTL
    )


async def clear_present(chat_id: int, user_id: int) -> None:
    """Снимает отметку присутствия (при закрытии WebSocket)."""
    await redis_client.delete(_presence_key(chat_id, user_id))


async def is_present(chat_id: int, user_id: int) -> bool:
    """Смотрит ли пользователь этот чат на сайте прямо сейчас."""
    return bool(await redis_client.exists(_presence_key(chat_id, user_id)))
