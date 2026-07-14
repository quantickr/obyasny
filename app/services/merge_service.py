"""Слияние двух аккаунтов: перенос всех данных src → dst и удаление src.

Используется при привязке Telegram, когда бот-аккаунт (создан через /start,
только telegram_id) нужно объединить с email-аккаунтом на сайте.

Все конфликты уникальных ключей предотвращаются проверками ДО записи, чтобы
не ронять транзакцию промежуточным flush. Итоговый commit делает вызывающий
слой (middleware бота).
"""

from __future__ import annotations

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, Message
from app.models.chocolate import ChocolateTransaction
from app.models.listing import Listing, ListingResponse
from app.models.match import Match
from app.models.request import Request
from app.models.topic import UserTopic
from app.models.user import User


async def merge_user_into(
    session: AsyncSession, src_id: int, dst_id: int
) -> None:
    """Переносит все данные пользователя src_id на dst_id и удаляет src_id.

    Снимает telegram_id со src и, если он был задан, ставит его на dst.
    """
    src = await session.get(User, src_id)
    dst = await session.get(User, dst_id)
    if src is None or dst is None:
        raise ValueError("merge_user_into: аккаунт не найден")

    tg_id = src.telegram_id
    tg_username = src.telegram_username

    # 1. user_topics — UNIQUE (user_id, topic_id, kind)
    dst_keys = set(
        await session.execute(
            select(UserTopic.topic_id, UserTopic.kind).where(
                UserTopic.user_id == dst_id
            )
        )
    )
    src_topics = list(
        await session.scalars(
            select(UserTopic).where(UserTopic.user_id == src_id)
        )
    )
    for ut in src_topics:
        if (ut.topic_id, ut.kind) in dst_keys:
            # У dst уже есть эта тема — перенесём оценку, если у dst пусто.
            existing = await session.scalar(
                select(UserTopic).where(
                    UserTopic.user_id == dst_id,
                    UserTopic.topic_id == ut.topic_id,
                    UserTopic.kind == ut.kind,
                )
            )
            if existing is not None and existing.level is None and ut.level is not None:
                existing.level = ut.level
            await session.delete(ut)
        else:
            ut.user_id = dst_id
            dst_keys.add((ut.topic_id, ut.kind))
    await session.flush()

    # 2. listings — без уникальных ограничений на author
    await session.execute(
        update(Listing).where(Listing.author_id == src_id).values(author_id=dst_id)
    )

    # 3. listing_responses — UNIQUE (listing_id, responder_id)
    dst_resp_listings = set(
        await session.scalars(
            select(ListingResponse.listing_id).where(
                ListingResponse.responder_id == dst_id
            )
        )
    )
    src_resps = list(
        await session.scalars(
            select(ListingResponse).where(ListingResponse.responder_id == src_id)
        )
    )
    for r in src_resps:
        if r.listing_id in dst_resp_listings:
            await session.delete(r)
        else:
            r.responder_id = dst_id
            dst_resp_listings.add(r.listing_id)
    await session.flush()

    # 4. requests — sender_id / receiver_id; self-request недопустим
    await session.execute(
        update(Request).where(Request.sender_id == src_id).values(sender_id=dst_id)
    )
    await session.execute(
        update(Request)
        .where(Request.receiver_id == src_id)
        .values(receiver_id=dst_id)
    )
    await session.execute(
        delete(Request).where(Request.sender_id == Request.receiver_id)
    )
    await session.flush()

    # 5. matches — CHECK (a<b) + UNIQUE; проще удалить все пары src (переподберутся)
    await session.execute(
        delete(Match).where(
            or_(Match.user_a_id == src_id, Match.user_b_id == src_id)
        )
    )
    await session.flush()

    # 6. chats — UNIQUE (user1_id, user2_id); нормализуем пару, self/дубль удаляем
    dst_pairs = set()
    for u1, u2 in await session.execute(
        select(Chat.user1_id, Chat.user2_id).where(
            or_(Chat.user1_id == dst_id, Chat.user2_id == dst_id)
        )
    ):
        dst_pairs.add((min(u1, u2), max(u1, u2)))
    src_chats = list(
        await session.scalars(
            select(Chat).where(
                or_(Chat.user1_id == src_id, Chat.user2_id == src_id)
            )
        )
    )
    for chat in src_chats:
        other = chat.user2_id if chat.user1_id == src_id else chat.user1_id
        if other == src_id or other == dst_id:
            # self-chat после переноса — удаляем (сообщения уйдут по CASCADE)
            await session.delete(chat)
            continue
        pair = (min(dst_id, other), max(dst_id, other))
        if pair in dst_pairs:
            # такой чат у dst уже есть — удаляем дубль src
            await session.delete(chat)
        else:
            chat.user1_id, chat.user2_id = pair
            dst_pairs.add(pair)
    await session.flush()

    # 7. messages — переносим авторство в оставшихся чатах
    await session.execute(
        update(Message).where(Message.sender_id == src_id).values(sender_id=dst_id)
    )
    await session.flush()

    # 8. chocolate_transactions — to/from; self-транзакции удаляем; баланс складываем
    await session.execute(
        update(ChocolateTransaction)
        .where(ChocolateTransaction.to_user_id == src_id)
        .values(to_user_id=dst_id)
    )
    await session.execute(
        update(ChocolateTransaction)
        .where(ChocolateTransaction.from_user_id == src_id)
        .values(from_user_id=dst_id)
    )
    await session.execute(
        delete(ChocolateTransaction).where(
            ChocolateTransaction.from_user_id == ChocolateTransaction.to_user_id
        )
    )
    dst.chocolate_balance = (dst.chocolate_balance or 0) + (
        src.chocolate_balance or 0
    )
    await session.flush()

    # 9. Удаляем src, затем привязываем его Telegram к dst.
    # Порядок важен: сначала удаляем строку src (освобождает UNIQUE
    # telegram_id и не нарушает CHECK ck_user_has_login_method), только
    # после этого присваиваем telegram_id получателю dst.
    await session.delete(src)
    await session.flush()
    if tg_id is not None:
        dst.telegram_id = tg_id
        dst.telegram_username = tg_username
    await session.flush()
