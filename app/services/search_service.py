from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.topic import Topic, TopicKind, UserTopic
from app.models.user import User


async def find_teachers(
    session: AsyncSession,
    topic_id: int,
    exclude_user_id: int,
    limit: int = 20,
) -> list[User]:
    """Кто может объяснить данную тему (can_teach), кроме самого искателя."""
    stmt = (
        select(User)
        .join(UserTopic, UserTopic.user_id == User.id)
        .where(
            UserTopic.topic_id == topic_id,
            UserTopic.kind == TopicKind.can_teach,
            User.id != exclude_user_id,
        )
        .order_by(UserTopic.level.desc().nullslast())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def find_teachers_by_query(
    session: AsyncSession,
    query: str,
    exclude_user_id: int,
    limit: int = 20,
) -> list[tuple[User, Topic]]:
    """Поиск преподающих по текстовому запросу темы. Возвращает (user, topic)."""
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(User, Topic)
        .join(UserTopic, UserTopic.user_id == User.id)
        .join(Topic, Topic.id == UserTopic.topic_id)
        .where(
            UserTopic.kind == TopicKind.can_teach,
            Topic.name.ilike(pattern),
            User.id != exclude_user_id,
        )
        .order_by(UserTopic.level.desc().nullslast())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]
