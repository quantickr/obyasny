from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_session_token
from app.models.user import User
from app.services import chocolate_service, user_service

SESSION_COOKIE = "session"

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user_optional(
    request: Request, session: SessionDep
) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    user_id = decode_session_token(token)
    if user_id is None:
        return None
    return await user_service.get_by_id(session, user_id)


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


class RequireLoginRedirect(Exception):
    pass


class RequireEmailVerification(Exception):
    """У пользователя есть email, но он не подтверждён — жёсткая блокировка."""


class RequireBanned(Exception):
    """Пользователь забанен админом — жёсткая блокировка входа."""


class RequireAdminAccess(Exception):
    """Требуется доступ администратора."""


async def get_current_user_allow_unverified(
    user: CurrentUserOptional,
) -> User:
    """Как get_current_user, но без проверки подтверждения email.

    Используется страницами подтверждения (/verify-email, resend), чтобы не
    зациклить редирект.
    """
    if user is None:
        raise RequireLoginRedirect()
    return user


CurrentUserUnverified = Annotated[
    User, Depends(get_current_user_allow_unverified)
]


async def get_current_user(
    user: CurrentUserOptional,
    session: SessionDep,
) -> User:
    if user is None:
        raise RequireLoginRedirect()
    # Забаненного пользователя не пускаем никуда, кроме страницы /banned.
    # Срочный бан автоснимается по истечении banned_until (ленивая проверка).
    if user.is_banned:
        if (
            user.banned_until is not None
            and user.banned_until <= datetime.now(timezone.utc)
        ):
            user.is_banned = False
            user.banned_until = None
            await session.commit()
        else:
            raise RequireBanned()
    # Жёсткая блокировка: email указан, но не подтверждён.
    # Telegram-аккаунты (email=None) не блокируются.
    if user.email is not None and not user.email_verified:
        raise RequireEmailVerification()
    # Ленивая еженедельная выдача шоколадок (планировщика нет): начисляем
    # при заходе на любую авторизованную страницу, если прошла неделя.
    granted = await chocolate_service.grant_weekly_if_due(session, user)
    if granted:
        await session.commit()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    """Требует прав администратора. Иначе — RequireAdminAccess."""
    if not user.is_admin:
        raise RequireAdminAccess()
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]


async def get_current_superadmin(admin: CurrentAdmin) -> User:
    """Требует прав главного администратора (управление админами)."""
    if not admin.is_superadmin:
        raise RequireAdminAccess()
    return admin


CurrentSuperadmin = Annotated[User, Depends(get_current_superadmin)]
