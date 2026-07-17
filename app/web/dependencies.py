from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import decode_session_token
from app.models.user import User
from app.services import user_service

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
) -> User:
    if user is None:
        raise RequireLoginRedirect()
    # Жёсткая блокировка: email указан, но не подтверждён.
    # Telegram-аккаунты (email=None) не блокируются.
    if user.email is not None and not user.email_verified:
        raise RequireEmailVerification()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
