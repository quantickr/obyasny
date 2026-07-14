from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ChatContext
from app.models.chocolate import ChocolateReason
from app.models.request import OfferType, Request, RequestStatus
from app.services import chat_service, chocolate_service


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
        .order_by(Request.created_at.desc())
    )
    return list(await session.scalars(stmt))


async def outgoing(session: AsyncSession, user_id: int) -> list[Request]:
    stmt = (
        select(Request)
        .where(Request.sender_id == user_id)
        .order_by(Request.created_at.desc())
    )
    return list(await session.scalars(stmt))


async def accept_request(
    session: AsyncSession, request_id: int, user_id: int
) -> Request:
    """Принять заявку: только получатель. Создаёт чат, награждает объясняющего."""
    req = await session.get(Request, request_id)
    if not req or req.receiver_id != user_id:
        raise RequestError("Заявка не найдена")
    if req.status != RequestStatus.pending:
        raise RequestError("Заявка уже обработана")

    chat = await chat_service.get_or_create_chat(
        session,
        req.sender_id,
        req.receiver_id,
        context_type=ChatContext.request,
        context_id=req.id,
    )
    req.status = RequestStatus.accepted
    req.chat_id = chat.id
    req.responded_at = datetime.now(timezone.utc)

    # Если оплата шоколадками — начисляем объясняющему (receiver).
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


async def decline_request(
    session: AsyncSession, request_id: int, user_id: int
) -> Request:
    req = await session.get(Request, request_id)
    if not req or req.receiver_id != user_id:
        raise RequestError("Заявка не найдена")
    if req.status != RequestStatus.pending:
        raise RequestError("Заявка уже обработана")
    req.status = RequestStatus.declined
    req.responded_at = datetime.now(timezone.utc)
    await session.flush()
    return req
