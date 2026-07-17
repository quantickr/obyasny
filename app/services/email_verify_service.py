import json
import secrets

from app.core.redis_client import redis_client

_PREFIX = "emailverify:"
_COOLDOWN_PREFIX = "emailverify:cooldown:"
_TTL_SECONDS = 900  # 15 минут — время жизни кода
_COOLDOWN_SECONDS = 60  # не чаще одного запроса кода в минуту
_MAX_ATTEMPTS = 5  # после стольких неверных вводов код сгорает


class TooSoonError(Exception):
    """Код запрашивали слишком часто (действует cooldown)."""


def _key(user_id: int) -> str:
    return f"{_PREFIX}{user_id}"


def _cooldown_key(user_id: int) -> str:
    return f"{_COOLDOWN_PREFIX}{user_id}"


async def issue_code(user_id: int, email: str) -> str:
    """Генерирует новый 6-значный код и кладёт в Redis (TTL 15 мин).

    Возвращает код для отправки письмом. Бросает TooSoonError, если код
    запрашивали меньше минуты назад.
    """
    cooldown = _cooldown_key(user_id)
    if await redis_client.exists(cooldown):
        raise TooSoonError("Код уже отправлен. Подождите минуту.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    payload = json.dumps(
        {"code": code, "email": email.lower().strip(), "attempts": 0}
    )
    await redis_client.set(_key(user_id), payload, ex=_TTL_SECONDS)
    await redis_client.set(cooldown, "1", ex=_COOLDOWN_SECONDS)
    return code


async def cooldown_ttl(user_id: int) -> int:
    """Сколько секунд осталось до возможности повторной отправки кода.

    0 — можно слать сразу (cooldown истёк/отсутствует). Используется для
    отрисовки обратного отсчёта на странице подтверждения почты.
    """
    ttl = await redis_client.ttl(_cooldown_key(user_id))
    return ttl if ttl and ttl > 0 else 0


async def verify_code(user_id: int, code: str) -> str | None:
    """Сверяет код. При успехе удаляет запись и возвращает подтверждённый email.

    При неверном коде инкрементит счётчик попыток; после _MAX_ATTEMPTS запись
    удаляется (нужно запросить код заново). Возвращает None при неудаче.
    """
    key = _key(user_id)
    raw = await redis_client.get(key)
    if raw is None:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        await redis_client.delete(key)
        return None

    if code.strip() == data.get("code"):
        email = data.get("email")
        await redis_client.delete(key)
        return email

    attempts = int(data.get("attempts", 0)) + 1
    if attempts >= _MAX_ATTEMPTS:
        await redis_client.delete(key)
        return None
    data["attempts"] = attempts
    # Сохраняем оставшийся TTL, чтобы код не «продлевался» при переборе.
    ttl = await redis_client.ttl(key)
    await redis_client.set(
        key, json.dumps(data), ex=ttl if ttl and ttl > 0 else _TTL_SECONDS
    )
    return None
