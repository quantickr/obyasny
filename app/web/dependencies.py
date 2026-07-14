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


async def get_current_user(
    user: CurrentUserOptional,
) -> User:
    if user is None:
        raise RequireLoginRedirect()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
