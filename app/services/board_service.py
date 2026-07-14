"""Доска студентов: пользователи с on_board=True и подсказки тем.

Доска строится напрямую из профилей (UserTopic), а не из отдельной модели
объявлений — источник истины по темам один, рассинхрона нет.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.topic import Topic, UserTopic
from app.models.user import User


async def list_board_users(
    session: AsyncSession, limit: int = 100
) -> list[User]:
    """Пользователи, выложенные на доску, с подгруженными темами."""
    stmt = (
        select(User)
        .where(User.on_board.is_(True))
        .options(
            selectinload(User.user_topics).selectinload(UserTopic.topic)
        )
        .order_by(User.id.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def toggle_board(session: AsyncSession, user: User) -> bool:
    """Переключает флаг on_board. Возвращает новое значение."""
    user.on_board = not user.on_board
    return user.on_board


async def board_topic_names(
    session: AsyncSession, q: str = "", limit: int = 10
) -> list[str]:
    """Названия тем, реально фигурирующих у пользователей на доске.

    Фильтрует по подстроке q (ILIKE) для автоподсказок в форме тем.
    """
    stmt = (
        select(Topic.name)
        .join(UserTopic, UserTopic.topic_id == Topic.id)
        .join(User, User.id == UserTopic.user_id)
        .where(User.on_board.is_(True))
    )
    if q.strip():
        stmt = stmt.where(Topic.name.ilike(f"%{q.strip()}%"))
    stmt = stmt.distinct().order_by(Topic.name).limit(limit)
    return list(await session.scalars(stmt))
