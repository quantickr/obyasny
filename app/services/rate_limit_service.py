"""Простой rate limiting на Redis (счётчик с окном).

Используется для защиты аутентификации от брутфорса и спама: логин, регистрация,
запрос кодов на почту. Ключ — действие + идентификатор (IP или email).
"""

from app.core.redis_client import redis_client

_PREFIX = "ratelimit:"


class RateLimitError(Exception):
    """Превышен лимит запросов для действия."""


async def hit(action: str, identifier: str, limit: int, window_seconds: int) -> None:
    """Инкрементит счётчик `action:identifier` и бросает RateLimitError,
    если за окно `window_seconds` число обращений превысило `limit`.

    Окно фиксированное: первый запрос ставит TTL, последующие только считают.
    """
    key = f"{_PREFIX}{action}:{identifier}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    if count > limit:
        raise RateLimitError(
            "Слишком много попыток. Подождите немного и попробуйте снова."
        )


async def reset(action: str, identifier: str) -> None:
    """Сбрасывает счётчик (например, после успешного входа)."""
    await redis_client.delete(f"{_PREFIX}{action}:{identifier}")


def client_ip(request) -> str:
    """IP клиента с учётом X-Forwarded-For (nginx проставляет реальный)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
