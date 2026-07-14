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
