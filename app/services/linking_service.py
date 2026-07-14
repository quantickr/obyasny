import secrets

from app.core.redis_client import redis_client

_PREFIX = "link:"
_TTL_SECONDS = 600  # 10 минут


async def generate_link_code(user_id: int) -> str:
    """Создаёт одноразовый код для привязки Telegram к веб-аккаунту."""
    code = secrets.token_urlsafe(6)
    await redis_client.set(f"{_PREFIX}{code}", str(user_id), ex=_TTL_SECONDS)
    return code


async def consume_link_code(code: str) -> int | None:
    """Возвращает user_id и удаляет код (одноразовость). None если невалиден."""
    key = f"{_PREFIX}{code}"
    user_id = await redis_client.get(key)
    if user_id is None:
        return None
    await redis_client.delete(key)
    try:
        return int(user_id)
    except ValueError:
        return None
