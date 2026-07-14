from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User


class AuthError(Exception):
    pass


async def get_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(
        select(User).where(User.email == email.lower().strip())
    )


async def get_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    return await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )


async def register_email(
    session: AsyncSession, email: str, password: str, display_name: str
) -> User:
    email = email.lower().strip()
    if await get_by_email(session, email):
        raise AuthError("Пользователь с таким email уже существует")
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=display_name.strip() or email.split("@")[0],
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate_email(
    session: AsyncSession, email: str, password: str
) -> User:
    user = await get_by_email(session, email)
    if not user or not user.password_hash:
        raise AuthError("Неверный email или пароль")
    if not verify_password(password, user.password_hash):
        raise AuthError("Неверный email или пароль")
    return user


async def get_or_create_telegram_user(
    session: AsyncSession,
    telegram_id: int,
    telegram_username: str | None,
    display_name: str,
) -> User:
    """Используется Telegram Login Widget и ботом при /start без кода."""
    user = await get_by_telegram_id(session, telegram_id)
    if user:
        if telegram_username and user.telegram_username != telegram_username:
            user.telegram_username = telegram_username
        return user
    user = User(
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        display_name=display_name.strip() or "Студент",
    )
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        # Гонка: параллельный /start уже создал этого пользователя между
        # нашим SELECT и INSERT. Откатываем и читаем существующую запись.
        await session.rollback()
        existing = await get_by_telegram_id(session, telegram_id)
        if existing is None:
            raise
        return existing
    return user


async def link_telegram(
    session: AsyncSession,
    user_id: int,
    telegram_id: int,
    telegram_username: str | None,
) -> User:
    """Привязка Telegram к существующему веб-аккаунту (через код линковки)."""
    user = await session.get(User, user_id)
    if not user:
        raise AuthError("Аккаунт не найден")
    # Если этот telegram_id уже привязан к другому пользователю — конфликт.
    other = await get_by_telegram_id(session, telegram_id)
    if other and other.id != user.id:
        raise AuthError("Этот Telegram уже привязан к другому аккаунту")
    user.telegram_id = telegram_id
    user.telegram_username = telegram_username
    return user


async def update_profile(
    session: AsyncSession,
    user: User,
    display_name: str | None = None,
    bio: str | None = None,
    show_tg_username: bool | None = None,
) -> User:
    if display_name is not None:
        user.display_name = display_name.strip()
    if bio is not None:
        user.bio = bio.strip()
    if show_tg_username is not None:
        user.show_tg_username = show_tg_username
    return user
