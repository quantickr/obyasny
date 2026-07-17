import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.profanity import clean_text, ensure_adequate, ensure_clean
from app.models.topic import Topic, TopicKind, UserTopic


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-") or "topic"


async def get_or_create_topic(
    session: AsyncSession, name: str, category: str | None = None
) -> Topic:
    clean_name = ensure_adequate(name)
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


def _clamp_price(price: int | None) -> int | None:
    """Цена в шоколадках: диапазон 1..3. None остаётся None (трактуется как 1)."""
    if price is None:
        return None
    return min(max(price, 1), 3)


async def set_user_topic(
    session: AsyncSession,
    user_id: int,
    topic: Topic,
    kind: TopicKind,
    level: int | None = None,
    details: str | None = None,
    price: int | None = None,
) -> UserTopic:
    if level is not None:
        level = min(max(level, 1), 10)
    # Цена — только для тем «могу объяснить»; для остальных обнуляем.
    price = _clamp_price(price) if kind == TopicKind.can_teach else None
    # Подробности («Подробнее») применимы к обоим видам тем.
    # Чистим от пробелов; пустое описание — это отсутствие описания.
    cleaned_details = clean_text(details)
    details = ensure_clean(cleaned_details) if cleaned_details else None
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
        existing.details = details
        existing.price = price
        return existing
    ut = UserTopic(
        user_id=user_id,
        topic_id=topic_id,
        kind=kind,
        level=level,
        details=details,
        price=price,
    )
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
        found.details = details
        found.price = price
        return found
    return ut


async def update_user_topic_level(
    session: AsyncSession,
    user_id: int,
    user_topic_id: int,
    level: int | None,
) -> UserTopic | None:
    """Меняет оценку у своей темы. level=None очищает оценку."""
    if level is not None:
        level = min(max(level, 1), 10)
    ut = await session.scalar(
        select(UserTopic).where(
            UserTopic.id == user_topic_id, UserTopic.user_id == user_id
        )
    )
    if ut is None:
        return None
    ut.level = level
    return ut


async def update_user_topic_price(
    session: AsyncSession,
    user_id: int,
    user_topic_id: int,
    price: int | None,
) -> UserTopic | None:
    """Меняет цену (в шоколадках) у своей темы «могу объяснить». Диапазон 1..3.

    price=None очищает цену (трактуется как 1). Применяется только к темам
    kind == can_teach; для остальных изменение игнорируется.
    """
    price = _clamp_price(price)
    ut = await session.scalar(
        select(UserTopic).where(
            UserTopic.id == user_topic_id, UserTopic.user_id == user_id
        )
    )
    if ut is None:
        return None
    if ut.kind == TopicKind.can_teach:
        ut.price = price
    return ut


async def update_user_topic_details(
    session: AsyncSession,
    user_id: int,
    user_topic_id: int,
    details: str | None,
) -> UserTopic | None:
    """Меняет описание («Подробнее») у своей темы.

    Чистит ввод от пробелов и проверяет на мат. Пустое описание
    (после очистки) очищает поле details.
    """
    cleaned = clean_text(details)
    cleaned = ensure_clean(cleaned) if cleaned else None
    ut = await session.scalar(
        select(UserTopic).where(
            UserTopic.id == user_topic_id, UserTopic.user_id == user_id
        )
    )
    if ut is None:
        return None
    ut.details = cleaned
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
