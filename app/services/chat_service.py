from datetime import datetime, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, ChatContext, Message, MessageSource


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
    stmt = (
        select(Chat)
        .where(or_(Chat.user1_id == user_id, Chat.user2_id == user_id))
        .order_by(Chat.id.desc())
    )
    return list(await session.scalars(stmt))


async def save_message(
    session: AsyncSession,
    chat_id: int,
    sender_id: int,
    body: str,
    source: MessageSource,
    tg_message_id: int | None = None,
    reply_to_id: int | None = None,
) -> Message:
    msg = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        body=body,
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
