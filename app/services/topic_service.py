import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.profanity import censor
from app.models.topic import Topic, TopicKind, UserTopic


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "topic"


async def get_or_create_topic(
    session: AsyncSession, name: str, category: str | None = None
) -> Topic:
    clean_name = censor(name.strip())
    slug = slugify(clean_name)
    existing = await session.scalar(select(Topic).where(Topic.slug == slug))
    if existing:
        return existing
    topic = Topic(name=clean_name, slug=slug, category=category)
    session.add(topic)
    try:
        await session.flush()
    except IntegrityError:
        # Гонка: параллельный запрос создал тему с тем же slug между
        # нашим SELECT и INSERT. Откатываем и читаем существующую запись.
        await session.rollback()
        found = await session.scalar(select(Topic).where(Topic.slug == slug))
        if found is None:
            raise
        return found
    return topic


async def search_topics(
    session: AsyncSession, query: str, limit: int = 10
) -> list[Topic]:
    """Нечёткий поиск тем по имени (ILIKE; при наличии pg_trgm — ранжирование)."""
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(Topic)
        .where(Topic.name.ilike(pattern))
        .order_by(func.length(Topic.name))
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def set_user_topic(
    session: AsyncSession,
    user_id: int,
    topic: Topic,
    kind: TopicKind,
    level: int | None = None,
) -> UserTopic:
    if level is not None:
        level = min(max(level, 1), 10)
    # Снимаем id заранее: после возможного rollback объект topic станет expired.
    topic_id = topic.id
    existing = await session.scalar(
        select(UserTopic).where(
            UserTopic.user_id == user_id,
            UserTopic.topic_id == topic_id,
            UserTopic.kind == kind,
        )
    )
    if existing:
        existing.level = level
        return existing
    ut = UserTopic(user_id=user_id, topic_id=topic_id, kind=kind, level=level)
    session.add(ut)
    try:
        await session.flush()
    except IntegrityError:
        # Гонка: параллельный запрос уже добавил эту тему пользователю
        # (нарушение uq_user_topic_kind). Откатываем и обновляем существующую.
        await session.rollback()
        found = await session.scalar(
            select(UserTopic).where(
                UserTopic.user_id == user_id,
                UserTopic.topic_id == topic_id,
                UserTopic.kind == kind,
            )
        )
        if found is None:
            raise
        found.level = level
        return found
    return ut


async def remove_user_topic(
    session: AsyncSession, user_id: int, user_topic_id: int
) -> None:
    ut = await session.scalar(
        select(UserTopic).where(
            UserTopic.id == user_topic_id, UserTopic.user_id == user_id
        )
    )
    if ut:
        await session.delete(ut)


async def get_user_topics(
    session: AsyncSession, user_id: int
) -> list[UserTopic]:
    stmt = (
        select(UserTopic)
        .where(UserTopic.user_id == user_id)
        .options(selectinload(UserTopic.topic))
        .order_by(UserTopic.kind, UserTopic.id)
    )
    return list(await session.scalars(stmt))
