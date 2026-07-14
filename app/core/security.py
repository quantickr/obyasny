import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def create_session_token(user_id: int) -> str:
    """JWT для httponly-cookie сессии."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(hours=settings.session_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> int | None:
    """Возвращает user_id или None, если токен невалиден/просрочен."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def verify_telegram_login(data: dict[str, str]) -> bool:
    """Проверка подписи Telegram Login Widget.

    Алгоритм: data_check_string из отсортированных k=v (кроме hash),
    секрет = sha256(bot_token), HMAC-SHA256 сравнивается с полем hash.
    """
    received_hash = data.get("hash")
    if not received_hash or not settings.bot_token:
        return False

    check_pairs = sorted(
        f"{k}={v}" for k, v in data.items() if k != "hash"
    )
    data_check_string = "\n".join(check_pairs)

    secret_key = hashlib.sha256(settings.bot_token.encode()).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hash, received_hash)
