from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.profanity import censor
from app.models.chat import Chat, ChatContext, Message, MessageSource
from app.models.chat_block import ChatBlock
from app.models.user import User


class MutedError(Exception):
    """Отправитель замучен админом и не может писать в чаты."""

    def __init__(self, until):
        self.until = until
        super().__init__("muted")


def _order_pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def get_or_create_chat(
    session: AsyncSession,
    user_a: int,
    user_b: int,
    context_type: ChatContext | None = None,
    context_id: int | None = None,
) -> Chat:
    u1, u2 = _order_pair(user_a, user_b)
    chat = await session.scalar(
        select(Chat).where(Chat.user1_id == u1, Chat.user2_id == u2)
    )
    if chat:
        return chat
    chat = Chat(
        user1_id=u1,
        user2_id=u2,
        context_type=context_type,
        context_id=context_id,
    )
    session.add(chat)
    await session.flush()
    return chat


async def create_request_chat(
    session: AsyncSession,
    user_a: int,
    user_b: int,
    title: str,
    context_id: int,
) -> Chat:
    """Всегда создаёт НОВЫЙ чат под конкретную заявку (context=request).

    В отличие от get_or_create_chat не переиспользует существующий чат пары —
    на каждую принятую заявку заводится отдельный чат с заголовком «Тема + Имя».
    """
    u1, u2 = _order_pair(user_a, user_b)
    chat = Chat(
        user1_id=u1,
        user2_id=u2,
        context_type=ChatContext.request,
        context_id=context_id,
        title=title,
    )
    session.add(chat)
    await session.flush()
    return chat


async def hide_chat(session: AsyncSession, chat_id: int, user_id: int) -> None:
    """«Удаляет» чат только у текущего пользователя (у собеседника остаётся)."""
    chat = await session.get(Chat, chat_id)
    if chat is None:
        return
    if chat.user1_id == user_id:
        chat.hidden_user1 = True
    elif chat.user2_id == user_id:
        chat.hidden_user2 = True
    await session.flush()


async def block_user(
    session: AsyncSession, blocker_id: int, blocked_id: int
) -> None:
    """Односторонне блокирует blocked_id «для себя» (blocker_id). Идемпотентно."""
    if blocker_id == blocked_id:
        return
    existing = await session.scalar(
        select(ChatBlock).where(
            ChatBlock.blocker_id == blocker_id,
            ChatBlock.blocked_id == blocked_id,
        )
    )
    if existing is not None:
        return
    session.add(ChatBlock(blocker_id=blocker_id, blocked_id=blocked_id))
    await session.flush()


async def unblock_user(
    session: AsyncSession, blocker_id: int, blocked_id: int
) -> None:
    block = await session.scalar(
        select(ChatBlock).where(
            ChatBlock.blocker_id == blocker_id,
            ChatBlock.blocked_id == blocked_id,
        )
    )
    if block is not None:
        await session.delete(block)
        await session.flush()


async def is_blocked(
    session: AsyncSession, blocker_id: int, blocked_id: int
) -> bool:
    """True, если blocker_id заблокировал blocked_id для себя."""
    block = await session.scalar(
        select(ChatBlock.id).where(
            ChatBlock.blocker_id == blocker_id,
            ChatBlock.blocked_id == blocked_id,
        )
    )
    return block is not None


async def blocked_ids(session: AsyncSession, blocker_id: int) -> set[int]:
    """ID пользователей, которых blocker_id заблокировал для себя."""
    rows = await session.scalars(
        select(ChatBlock.blocked_id).where(
            ChatBlock.blocker_id == blocker_id
        )
    )
    return set(rows)


async def complete_chat(session: AsyncSession, chat_id: int) -> None:
    """Помечает чат завершённым (read-only, серый, вниз списка)."""
    chat = await session.get(Chat, chat_id)
    if chat is not None and chat.completed_at is None:
        chat.completed_at = datetime.now(timezone.utc)
        await session.flush()


async def get_chat_for_user(
    session: AsyncSession, chat_id: int, user_id: int
) -> Chat | None:
    return await session.scalar(
        select(Chat).where(
            Chat.id == chat_id,
            or_(Chat.user1_id == user_id, Chat.user2_id == user_id),
        )
    )


def other_participant(chat: Chat, user_id: int) -> int:
    return chat.user2_id if chat.user1_id == user_id else chat.user1_id


async def list_user_chats(session: AsyncSession, user_id: int) -> list[Chat]:
    """Чаты пользователя: незавершённые сверху, завершённые внизу.

    Исключаем чаты, скрытые текущим пользователем (hidden_user1/2 по позиции).
    """
    stmt = (
        select(Chat)
        .where(
            or_(Chat.user1_id == user_id, Chat.user2_id == user_id),
            # Не показываем чаты, которые текущий юзер «удалил» у себя.
            or_(
                and_(Chat.user1_id == user_id, Chat.hidden_user1.is_(False)),
                and_(Chat.user2_id == user_id, Chat.hidden_user2.is_(False)),
            ),
        )
        # completed_at IS NULL сортируется как «меньше» → завершённые уходят вниз.
        .order_by(Chat.completed_at.isnot(None), Chat.id.desc())
    )
    chats = list(await session.scalars(stmt))
    # Личная блокировка «для себя»: прячем чаты с заблокированными собеседниками.
    blocked = await blocked_ids(session, user_id)
    if blocked:
        chats = [
            c for c in chats if other_participant(c, user_id) not in blocked
        ]
    return chats


async def save_message(
    session: AsyncSession,
    chat_id: int,
    sender_id: int,
    body: str,
    source: MessageSource,
    tg_message_id: int | None = None,
    reply_to_id: int | None = None,
) -> Message:
    # Мут: замученный пользователь не может писать в чаты (веб + Telegram).
    # Единая точка проверки для обоих каналов.
    sender = await session.get(User, sender_id)
    if (
        sender is not None
        and sender.muted_until is not None
        and sender.muted_until > datetime.now(timezone.utc)
    ):
        raise MutedError(sender.muted_until)
    # Модерация: маскируем мат/угрозы на '*' (не отклоняем, чтобы диалог
    # не рвался). Единая точка для веба и Telegram-бота.
    msg = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        body=censor(body),
        source=source,
        tg_message_id=tg_message_id,
        reply_to_id=reply_to_id,
    )
    session.add(msg)
    await session.flush()
    return msg


async def find_message_by_tg_id(
    session: AsyncSession, chat_id: int, tg_message_id: int
) -> Message | None:
    """Ищет сообщение чата по id сообщения в Telegram (для сопоставления reply)."""
    return await session.scalar(
        select(Message).where(
            Message.chat_id == chat_id,
            Message.tg_message_id == tg_message_id,
        )
    )


async def find_message_by_tg_id_for_user(
    session: AsyncSession, user_id: int, tg_message_id: int
) -> Message | None:
    """Ищет сообщение по tg_message_id в любом чате, где участвует user_id.

    Нужно для reply из Telegram вне режима активного чата: по id
    сообщения-уведомления находим чат и цитируемое сообщение.
    """
    return await session.scalar(
        select(Message)
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Message.tg_message_id == tg_message_id,
            or_(Chat.user1_id == user_id, Chat.user2_id == user_id),
        )
    )


async def get_messages(
    session: AsyncSession, chat_id: int, limit: int = 100
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def mark_chat_read(
    session: AsyncSession, chat_id: int, user_id: int
) -> None:
    """Помечает входящие (не свои) непрочитанные сообщения чата прочитанными."""
    await session.execute(
        update(Message)
        .where(
            Message.chat_id == chat_id,
            Message.sender_id != user_id,
            Message.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )


async def unread_total(session: AsyncSession, user_id: int) -> int:
    """Число непрочитанных входящих сообщений во всех чатах пользователя."""
    stmt = (
        select(func.count(Message.id))
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Message.sender_id != user_id,
            Message.read_at.is_(None),
            or_(Chat.user1_id == user_id, Chat.user2_id == user_id),
        )
    )
    return int(await session.scalar(stmt) or 0)


async def unread_messages(
    session: AsyncSession, chat_id: int, user_id: int
) -> list[Message]:
    """Непрочитанные входящие (не свои) сообщения чата в хронологическом порядке."""
    stmt = (
        select(Message)
        .where(
            Message.chat_id == chat_id,
            Message.sender_id != user_id,
            Message.read_at.is_(None),
        )
        .order_by(Message.created_at.asc())
    )
    return list(await session.scalars(stmt))


async def unread_by_chat(
    session: AsyncSession, user_id: int
) -> dict[int, int]:
    """Число непрочитанных входящих по каждому чату пользователя."""
    stmt = (
        select(Message.chat_id, func.count(Message.id))
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Message.sender_id != user_id,
            Message.read_at.is_(None),
            or_(Chat.user1_id == user_id, Chat.user2_id == user_id),
        )
        .group_by(Message.chat_id)
    )
    rows = await session.execute(stmt)
    return {chat_id: count for chat_id, count in rows.all()}


async def last_message_by_chat(
    session: AsyncSession, chat_ids: list[int]
) -> dict[int, Message]:
    """Последнее сообщение для каждого из указанных чатов."""
    if not chat_ids:
        return {}
    result: dict[int, Message] = {}
    stmt = (
        select(Message)
        .where(Message.chat_id.in_(chat_ids))
        .order_by(Message.created_at.desc())
    )
    for msg in await session.scalars(stmt):
        if msg.chat_id not in result:
            result[msg.chat_id] = msg
    return result
