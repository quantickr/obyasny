"""Доска студентов: пользователи с on_board=True и подсказки тем.

Доска строится напрямую из профилей (UserTopic), а не из отдельной модели
объявлений — источник истины по темам один, рассинхрона нет.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.topic import Topic, TopicKind, UserTopic
from app.models.user import User

# Категории приоритета для персональной сортировки доски.
MATCH_PERFECT = 3  # взаимный обмен: учит нужное мне И хочет то, что я умею
MATCH_CAN_HELP_ME = 2  # может объяснить то, что я хочу узнать
MATCH_I_CAN_HELP = 1  # хочет узнать то, что я умею объяснить
MATCH_NONE = 0


@dataclass
class BoardCard:
    student: User
    can_teach: list[UserTopic]
    wants_learn: list[UserTopic]
    match_kind: int


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


async def list_board_cards_plain(
    session: AsyncSession, limit: int = 100
) -> list[BoardCard]:
    """Карточки доски без персонального ранжирования — для гостей.

    Порядок как у list_board_users (свежие сверху), match_kind = MATCH_NONE.
    """
    users = await list_board_users(session, limit=limit)
    cards: list[BoardCard] = []
    for u in users:
        can_teach = [
            ut for ut in u.user_topics if ut.kind == TopicKind.can_teach
        ]
        wants_learn = [
            ut for ut in u.user_topics if ut.kind == TopicKind.wants_learn
        ]
        cards.append(BoardCard(u, can_teach, wants_learn, MATCH_NONE))
    return cards


async def list_board_cards_ranked(
    session: AsyncSession, viewer_id: int, limit: int = 100
) -> list[BoardCard]:
    """Карточки доски, персонально отсортированные для viewer.

    Порядок: идеальные метчи → кто может помочь мне → кому могу помочь я →
    остальные. Внутри категории — по числу совпадений тем.
    """
    users = await list_board_users(session, limit=limit)

    # Темы текущего пользователя.
    my_teach: set[int] = set()
    my_learn: set[int] = set()
    my_rows = await session.scalars(
        select(UserTopic).where(UserTopic.user_id == viewer_id)
    )
    for ut in my_rows:
        if ut.kind == TopicKind.can_teach:
            my_teach.add(ut.topic_id)
        elif ut.kind == TopicKind.wants_learn:
            my_learn.add(ut.topic_id)

    cards: list[tuple[BoardCard, int]] = []
    for u in users:
        can_teach = [
            ut for ut in u.user_topics if ut.kind == TopicKind.can_teach
        ]
        wants_learn = [
            ut for ut in u.user_topics if ut.kind == TopicKind.wants_learn
        ]
        if u.id == viewer_id:
            # Своя карточка всегда внизу, без метча.
            cards.append(
                (BoardCard(u, can_teach, wants_learn, MATCH_NONE), -1)
            )
            continue

        cand_teach = {ut.topic_id for ut in can_teach}
        cand_learn = {ut.topic_id for ut in wants_learn}
        helps_me = cand_teach & my_learn  # он учит то, что я хочу
        i_help = cand_learn & my_teach  # он хочет то, что я умею
        overlap = len(helps_me) + len(i_help)

        if helps_me and i_help:
            kind = MATCH_PERFECT
        elif helps_me:
            kind = MATCH_CAN_HELP_ME
        elif i_help:
            kind = MATCH_I_CAN_HELP
        else:
            kind = MATCH_NONE
        cards.append(
            (BoardCard(u, can_teach, wants_learn, kind), overlap)
        )

    # Сортировка: сначала по категории (убыв.), затем по числу совпадений.
    cards.sort(key=lambda pair: (pair[0].match_kind, pair[1]), reverse=True)
    return [card for card, _ in cards]


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
