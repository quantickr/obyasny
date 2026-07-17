from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.profanity import ensure_clean
from app.core.security import hash_password, verify_password
from app.models.user import EduLevel, User
from app.services import chocolate_service


class AuthError(Exception):
    pass


#: Максимальный номер курса/класса по уровню образования.
#: schoolchild — 11 классов, bachelor — 5, specialist — 6, master — 3,
#: postgrad — 4. Значение по умолчанию (11) — на случай неизвестного уровня.
MAX_COURSE_BY_LEVEL: dict[EduLevel, int] = {
    EduLevel.schoolchild: 11,
    EduLevel.bachelor: 5,
    EduLevel.specialist: 6,
    EduLevel.master: 3,
    EduLevel.postgrad: 4,
}


def clamp_course(course: int, level: EduLevel | None) -> int:
    """Ограничивает курс диапазоном 1..max, где max зависит от уровня."""
    upper = MAX_COURSE_BY_LEVEL.get(level, 11) if level is not None else 11
    return min(max(course, 1), upper)


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


async def set_banned(
    session: AsyncSession, user_id: int, banned: bool
) -> User | None:
    """Бан/разбан пользователя админом."""
    user = await session.get(User, user_id)
    if user is None:
        return None
    user.is_banned = banned
    await session.flush()
    return user


async def list_users(
    session: AsyncSession, query: str | None = None, limit: int = 100
) -> list[User]:
    """Список пользователей для админки. query фильтрует по имени/email."""
    stmt = select(User)
    if query:
        pattern = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.display_name).like(pattern),
                func.lower(User.email).like(pattern),
            )
        )
    stmt = stmt.order_by(User.id.desc()).limit(limit)
    return list(await session.scalars(stmt))


async def count_users(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(User.id))) or 0)


async def register_email(
    session: AsyncSession,
    email: str,
    password: str,
    display_name: str,
    university: str,
    course: int,
    edu_level: EduLevel,
) -> User:
    email = email.lower().strip()
    if await get_by_email(session, email):
        raise AuthError("Пользователь с таким email уже существует")
    user = User(
        email=email,
        password_hash=hash_password(password),
        display_name=ensure_clean(display_name.strip()) or email.split("@")[0],
        university=ensure_clean(university.strip()),
        course=clamp_course(course, edu_level),
        edu_level=edu_level,
    )
    session.add(user)
    await session.flush()
    # Стартовый бонус: 5 шоколадок при регистрации.
    await chocolate_service.award_signup_bonus(session, user.id)
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


async def set_email_verified(session: AsyncSession, user: User) -> None:
    """Помечает email пользователя подтверждённым."""
    user.email_verified = True


async def reset_password(
    session: AsyncSession, user: User, new_password: str
) -> None:
    """Устанавливает новый пароль пользователю (после сброса по коду)."""
    user.password_hash = hash_password(new_password)


async def change_email(session: AsyncSession, user: User, new_email: str) -> None:
    """Меняет/добавляет email пользователю и сбрасывает подтверждение.

    Бросает AuthError, если email уже занят другим аккаунтом.
    """
    new_email = new_email.lower().strip()
    if not new_email:
        raise AuthError("Укажите email")
    existing = await get_by_email(session, new_email)
    if existing and existing.id != user.id:
        raise AuthError("Пользователь с таким email уже существует")
    if existing and existing.id == user.id and user.email_verified:
        # Тот же самый уже подтверждённый email — ничего не делаем.
        raise AuthError("Это ваш текущий email")
    user.email = new_email
    user.email_verified = False


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
        # Учебные поля NOT NULL: заглушки. Пустой university — маркер
        # незаполненности, пользователь дозаполнит в профиле.
        university="",
        course=1,
        edu_level=EduLevel.bachelor,
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
    # Стартовый бонус: 5 шоколадок при регистрации через Telegram.
    await chocolate_service.award_signup_bonus(session, user.id)
    return user


async def link_or_merge_telegram(
    session: AsyncSession,
    user_id: int,
    telegram_id: int,
    telegram_username: str | None,
) -> tuple[User, bool]:
    """Привязка Telegram к веб-аккаунту (через код линковки).

    Если telegram_id уже принадлежит отдельному «пустому» бот-аккаунту
    (только telegram_id, без email/пароля) — сливаем его данные в текущий
    аккаунт и удаляем бот-аккаунт. Если он привязан к полноценному аккаунту
    с почтой — отказ.

    Возвращает (пользователь, было_ли_слияние).
    """
    from app.services import merge_service

    user = await session.get(User, user_id)
    if not user:
        raise AuthError("Аккаунт не найден")

    # Идемпотентность: уже привязан этот же Telegram.
    if user.telegram_id == telegram_id:
        return user, False
    # У аккаунта уже есть ДРУГОЙ Telegram.
    if user.telegram_id is not None and user.telegram_id != telegram_id:
        raise AuthError("К этому аккаунту уже привязан другой Telegram")

    other = await get_by_telegram_id(session, telegram_id)
    if other is None:
        # Простая привязка — telegram_id свободен.
        user.telegram_id = telegram_id
        user.telegram_username = telegram_username
        return user, False
    if other.id == user.id:
        return user, False

    # telegram_id принадлежит другому аккаунту.
    if other.email or other.password_hash:
        raise AuthError("Этот Telegram привязан к отдельному аккаунту с почтой")

    # other — чисто бот-аккаунт: сливаем его данные в текущий и удаляем.
    await merge_service.merge_user_into(session, src_id=other.id, dst_id=user.id)
    await session.refresh(user)
    return user, True


async def update_profile(
    session: AsyncSession,
    user: User,
    display_name: str | None = None,
    bio: str | None = None,
    show_tg_username: bool | None = None,
    university: str | None = None,
    course: int | None = None,
    edu_level: EduLevel | None = None,
    avatar_url: str | None = None,
) -> User:
    if display_name is not None:
        user.display_name = ensure_clean(display_name.strip())
    if bio is not None:
        user.bio = ensure_clean(bio.strip())
    if show_tg_username is not None:
        user.show_tg_username = show_tg_username
    if university is not None:
        user.university = ensure_clean(university.strip())
    if edu_level is not None:
        user.edu_level = edu_level
    if course is not None:
        # Валидируем курс по итоговому уровню (только что заданному или текущему),
        # чтобы, например, у бакалавра нельзя было выставить 8-й курс.
        user.course = clamp_course(course, user.edu_level)
    if avatar_url is not None:
        user.avatar_url = avatar_url
    return user
