import json
import secrets

from app.core.redis_client import redis_client

_PREFIX = "pwreset:"
_COOLDOWN_PREFIX = "pwreset:cooldown:"
_TTL_SECONDS = 900  # 15 минут — время жизни кода
_COOLDOWN_SECONDS = 60  # не чаще одного запроса кода в минуту
_MAX_ATTEMPTS = 5  # после стольких неверных вводов код сгорает


class TooSoonError(Exception):
    """Код запрашивали слишком часто (действует cooldown)."""


def _norm(email: str) -> str:
    return email.lower().strip()


def _key(email: str) -> str:
    return f"{_PREFIX}{_norm(email)}"


def _cooldown_key(email: str) -> str:
    return f"{_COOLDOWN_PREFIX}{_norm(email)}"


async def issue_code(email: str) -> str:
    """Генерирует 6-значный код для сброса пароля и кладёт в Redis (TTL 15 мин).

    Ключ привязан к email (пользователь не залогинен). Бросает TooSoonError,
    если код запрашивали меньше минуты назад.
    """
    cooldown = _cooldown_key(email)
    if await redis_client.exists(cooldown):
        raise TooSoonError("Код уже отправлен. Подождите минуту.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    payload = json.dumps({"code": code, "attempts": 0})
    await redis_client.set(_key(email), payload, ex=_TTL_SECONDS)
    await redis_client.set(cooldown, "1", ex=_COOLDOWN_SECONDS)
    return code


async def verify_code(email: str, code: str) -> bool:
    """Сверяет код. При успехе удаляет запись и возвращает True.

    При неверном коде инкрементит счётчик попыток; после _MAX_ATTEMPTS запись
    удаляется (нужно запросить код заново). Возвращает False при неудаче.
    """
    key = _key(email)
    raw = await redis_client.get(key)
    if raw is None:
        return False
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        await redis_client.delete(key)
        return False

    if code.strip() == data.get("code"):
        await redis_client.delete(key)
        return True

    attempts = int(data.get("attempts", 0)) + 1
    if attempts >= _MAX_ATTEMPTS:
        await redis_client.delete(key)
        return False
    data["attempts"] = attempts
    # Сохраняем оставшийся TTL, чтобы код не «продлевался» при переборе.
    ttl = await redis_client.ttl(key)
    await redis_client.set(
        key, json.dumps(data), ex=ttl if ttl and ttl > 0 else _TTL_SECONDS
    )
    return False
