from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.profanity import ProfanityError, ensure_clean
from app.models.chocolate import ChocolateReason
from app.models.request import OfferType, Request, RequestStatus
from app.models.topic import Topic
from app.models.user import User
from app.services import chat_service, chocolate_service
from app.services.chocolate_service import NotEnoughChocolates

# Длительности блокировки при отказе. "forever" → далёкая дата.
_FOREVER = datetime(9999, 12, 31, tzinfo=timezone.utc)
_BLOCK_DURATIONS: dict[str, timedelta | None] = {
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}


class RequestError(Exception):
    pass


async def create_request(
    session: AsyncSession,
    sender_id: int,
    receiver_id: int,
    topic_id: int,
    message: str | None = None,
    offer_type: OfferType = OfferType.chocolates,
    offer_topic_id: int | None = None,
) -> Request:
    if sender_id == receiver_id:
        raise RequestError("Нельзя отправить заявку самому себе")

    try:
        message = ensure_clean(message)
    except ProfanityError as e:
        raise RequestError(str(e)) from e

    # Одна активная заявка на пару (sender→receiver) по всем темам.
    active = await session.scalar(
        select(Request).where(
            Request.sender_id == sender_id,
            Request.receiver_id == receiver_id,
            Request.status == RequestStatus.pending,
        )
    )
    if active is not None:
        raise RequestError(
            "Заявка этому пользователю уже отправлена и ожидает ответа"
        )

    # После принятия повторно слать нельзя.
    accepted = await session.scalar(
        select(Request).where(
            Request.sender_id == sender_id,
            Request.receiver_id == receiver_id,
            Request.status == RequestStatus.accepted,
        )
    )
    if accepted is not None:
        raise RequestError("Вы уже связаны с этим пользователем")

    # Действующая блокировка после отказа.
    now = datetime.now(timezone.utc)
    blocked = await session.scalar(
        select(Request).where(
            Request.sender_id == sender_id,
            Request.receiver_id == receiver_id,
            Request.blocked_until.is_not(None),
            Request.blocked_until > now,
        )
    )
    if blocked is not None:
        raise RequestError(
            "Пользователь временно не принимает от вас заявки"
        )

    req = Request(
        sender_id=sender_id,
        receiver_id=receiver_id,
        topic_id=topic_id,
        message=message,
        offer_type=offer_type,
        offer_topic_id=offer_topic_id,
        status=RequestStatus.pending,
    )
    session.add(req)
    await session.flush()

    # Экономика: заявка «за шоколадки» списывает 1 шоколадку у отправителя
    # сразу при отправке. Возврат — при отказе/отмене; при завершении задачи
    # шоколадка достаётся объясняющему.
    if offer_type == OfferType.chocolates:
        try:
            await chocolate_service.spend(
                session,
                user_id=sender_id,
                amount=1,
                reason=ChocolateReason.spend,
                ref_type="request",
                ref_id=req.id,
            )
        except NotEnoughChocolates as e:
            raise RequestError("Недостаточно шоколадок для отправки заявки") from e

    return req


async def get_request(session: AsyncSession, request_id: int) -> Request | None:
    return await session.get(Request, request_id)


async def incoming(session: AsyncSession, user_id: int) -> list[Request]:
    stmt = (
        select(Request)
        .where(
            Request.receiver_id == user_id,
            Request.status == RequestStatus.pending,
        )
        .options(
            selectinload(Request.sender),
            selectinload(Request.topic),
        )
        .order_by(Request.created_at.desc())
    )
    return list(await session.scalars(stmt))


async def outgoing(session: AsyncSession, user_id: int) -> list[Request]:
    stmt = (
        select(Request)
        .where(Request.sender_id == user_id)
        .options(
            selectinload(Request.receiver),
            selectinload(Request.topic),
        )
        .order_by(Request.created_at.desc())
    )
    return list(await session.scalars(stmt))


async def active(session: AsyncSession, user_id: int) -> list[Request]:
    """Принятые (в работе) заявки, где пользователь — sender или receiver.

    Нужны для кнопки «Завершить» на /requests: завершать может любая сторона.
    """
    stmt = (
        select(Request)
        .where(
            or_(
                Request.sender_id == user_id,
                Request.receiver_id == user_id,
            ),
            Request.status == RequestStatus.accepted,
        )
        .options(
            selectinload(Request.sender),
            selectinload(Request.receiver),
            selectinload(Request.topic),
        )
        .order_by(Request.responded_at.desc())
    )
    return list(await session.scalars(stmt))


async def incoming_count(session: AsyncSession, user_id: int) -> int:
    """Число входящих заявок, ожидающих ответа."""
    stmt = select(func.count(Request.id)).where(
        Request.receiver_id == user_id,
        Request.status == RequestStatus.pending,
    )
    return int(await session.scalar(stmt) or 0)


async def accept_request(
    session: AsyncSession, request_id: int, user_id: int
) -> Request:
    """Принять заявку: только получатель. Создаёт отдельный чат под заявку.

    Заголовок чата = «Тема + Имя отправителя». Награда объясняющему НЕ
    начисляется здесь — только при обоюдном завершении задачи (toggle_done).
    """
    req = await session.get(Request, request_id)
    if not req or req.receiver_id != user_id:
        raise RequestError("Заявка не найдена")
    if req.status != RequestStatus.pending:
        raise RequestError("Заявка уже обработана")

    topic = await session.get(Topic, req.topic_id)
    sender = await session.get(User, req.sender_id)
    topic_name = topic.name if topic else "Тема"
    sender_name = sender.display_name if sender else "Пользователь"
    title = f"{topic_name} — {sender_name}"

    chat = await chat_service.create_request_chat(
        session,
        req.sender_id,
        req.receiver_id,
        title=title,
        context_id=req.id,
    )
    req.status = RequestStatus.accepted
    req.chat_id = chat.id
    req.responded_at = datetime.now(timezone.utc)
    await session.flush()
    return req


async def _refund_if_chocolates(session: AsyncSession, req: Request) -> None:
    """Возвращает списанную шоколадку отправителю при отказе/отмене заявки."""
    if req.offer_type == OfferType.chocolates:
        await chocolate_service.award(
            session,
            to_user_id=req.sender_id,
            amount=1,
            reason=ChocolateReason.refund,
            ref_type="request",
            ref_id=req.id,
        )


async def decline_request(
    session: AsyncSession, request_id: int, user_id: int, block: str = "forever"
) -> Request:
    """Отклонить заявку. block ∈ {forever, month, week, day, none} задаёт срок,
    в течение которого отправитель не может слать новые заявки получателю."""
    req = await session.get(Request, request_id)
    if not req or req.receiver_id != user_id:
        raise RequestError("Заявка не найдена")
    if req.status != RequestStatus.pending:
        raise RequestError("Заявка уже обработана")
    req.status = RequestStatus.declined
    req.responded_at = datetime.now(timezone.utc)
    req.blocked_until = _blocked_until(block)
    await _refund_if_chocolates(session, req)
    await session.flush()
    return req


async def decline_all_from(
    session: AsyncSession, request_id: int, user_id: int, block: str = "forever"
) -> None:
    """Отклонить все pending-заявки от отправителя этой заявки к получателю.

    Блокирует отправителя на срок block для всех отклонённых заявок.
    """
    req = await session.get(Request, request_id)
    if not req or req.receiver_id != user_id:
        raise RequestError("Заявка не найдена")

    sender_id = req.sender_id
    blocked_until = _blocked_until(block)
    now = datetime.now(timezone.utc)
    pending = await session.scalars(
        select(Request).where(
            Request.sender_id == sender_id,
            Request.receiver_id == user_id,
            Request.status == RequestStatus.pending,
        )
    )
    for r in pending:
        r.status = RequestStatus.declined
        r.responded_at = now
        r.blocked_until = blocked_until
        await _refund_if_chocolates(session, r)
    await session.flush()


async def toggle_done(
    session: AsyncSession, request_id: int, user_id: int
) -> Request:
    """Отметка «Завершить» одной из сторон. Завершение — по обоюдному согласию.

    Только участник заявки (sender/receiver) может отметить. Когда оба отметили
    → status=completed, чат становится завершённым, объясняющему (receiver)
    начисляется 1 шоколадка (та, что списалась у отправителя при создании).
    """
    req = await session.get(Request, request_id)
    if not req:
        raise RequestError("Заявка не найдена")
    if user_id not in (req.sender_id, req.receiver_id):
        raise RequestError("Нет доступа к заявке")
    if req.status not in (RequestStatus.accepted,):
        raise RequestError("Заявку нельзя завершить")

    if user_id == req.sender_id:
        req.sender_done = True
    else:
        req.receiver_done = True

    if req.sender_done and req.receiver_done:
        req.status = RequestStatus.completed
        req.completed_at = datetime.now(timezone.utc)
        if req.chat_id is not None:
            await chat_service.complete_chat(session, req.chat_id)
        # Награда объясняющему (receiver) — только для оплаты шоколадками.
        if req.offer_type == OfferType.chocolates:
            await chocolate_service.award(
                session,
                to_user_id=req.receiver_id,
                amount=1,
                reason=ChocolateReason.explanation,
                from_user_id=req.sender_id,
                ref_type="request",
                ref_id=req.id,
            )
    await session.flush()
    return req


def _blocked_until(block: str) -> datetime | None:
    if block == "none":
        return None
    if block == "forever":
        return _FOREVER
    delta = _BLOCK_DURATIONS.get(block)
    if delta is None:
        return None
    return datetime.now(timezone.utc) + delta
