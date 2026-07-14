from sqlalchemy import or_, select
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
) -> Message:
    msg = Message(
        chat_id=chat_id,
        sender_id=sender_id,
        body=body,
        source=source,
        tg_message_id=tg_message_id,
    )
    session.add(msg)
    await session.flush()
    return msg


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
