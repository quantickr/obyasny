from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.profanity import ProfanityError, ensure_clean
from app.models.chat import Message, MessageSource
from app.models.chocolate import ChocolateReason
from app.models.request import OfferType, Request, RequestStatus
from app.models.topic import Topic, TopicKind, UserTopic
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


async def _teach_price(
    session: AsyncSession, receiver_id: int, topic_id: int
) -> int:
    """Цена в шоколадках за объяснение темы `topic_id` пользователем `receiver_id`.

    Берётся из его темы «могу объяснить» (kind == can_teach). Диапазон 0..3,
    где 0 — бесплатно. Тема без цены (price is None) или отсутствует → 1
    (обратная совместимость).
    """
    ut = await session.scalar(
        select(UserTopic).where(
            UserTopic.user_id == receiver_id,
            UserTopic.topic_id == topic_id,
            UserTopic.kind == TopicKind.can_teach,
        )
    )
    if ut is None or ut.price is None:
        return 1
    return ut.price


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

    # Одна активная заявка на пару (sender→receiver) ПО ЭТОЙ ТЕМЕ.
    active = await session.scalar(
        select(Request).where(
            Request.sender_id == sender_id,
            Request.receiver_id == receiver_id,
            Request.topic_id == topic_id,
            Request.status == RequestStatus.pending,
        )
    )
    if active is not None:
        raise RequestError(
            "Заявка этому пользователю по этой теме уже отправлена и ожидает ответа"
        )

    # После принятия повторно слать по ЭТОЙ ЖЕ теме нельзя.
    accepted = await session.scalar(
        select(Request).where(
            Request.sender_id == sender_id,
            Request.receiver_id == receiver_id,
            Request.topic_id == topic_id,
            Request.status == RequestStatus.accepted,
        )
    )
    if accepted is not None:
        raise RequestError("Вы уже связаны с этим пользователем по этой теме")

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

    # Цена фиксируется в заявке в момент создания (из темы объясняющего),
    # чтобы возврат/награда позже совпали со списанием, даже если учитель
    # поменяет цену темы.
    price = await _teach_price(session, receiver_id, topic_id)

    req = Request(
        sender_id=sender_id,
        receiver_id=receiver_id,
        topic_id=topic_id,
        message=message,
        offer_type=offer_type,
        offer_topic_id=offer_topic_id,
        status=RequestStatus.pending,
        price=price,
    )
    session.add(req)
    await session.flush()

    # Экономика: заявка «за шоколадки» списывает цену темы у отправителя сразу
    # при отправке. Возврат — при отказе/отмене; при завершении задачи шоколадки
    # достаются объясняющему. При цене 0 (бесплатно) ничего не списывается и
    # баланс не проверяется.
    if offer_type == OfferType.chocolates and price > 0:
        try:
            await chocolate_service.spend(
                session,
                user_id=sender_id,
                amount=price,
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
    """Исходящие заявки, ожидающие ответа (pending). Принятые — в active(),
    завершённые — в completed(), отклонённые — в declined()."""
    stmt = (
        select(Request)
        .where(
            Request.sender_id == user_id,
            Request.status == RequestStatus.pending,
        )
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


async def completed(session: AsyncSession, user_id: int) -> list[Request]:
    """Завершённые заявки, где пользователь — sender или receiver."""
    stmt = (
        select(Request)
        .where(
            or_(
                Request.sender_id == user_id,
                Request.receiver_id == user_id,
            ),
            Request.status == RequestStatus.completed,
        )
        .options(
            selectinload(Request.sender),
            selectinload(Request.receiver),
            selectinload(Request.topic),
        )
        .order_by(Request.completed_at.desc())
    )
    return list(await session.scalars(stmt))


async def declined(session: AsyncSession, user_id: int) -> list[Request]:
    """Отклонённые исходящие заявки пользователя (кому и по какой теме отказали)."""
    stmt = (
        select(Request)
        .where(
            Request.sender_id == user_id,
            Request.status == RequestStatus.declined,
        )
        .options(
            selectinload(Request.receiver),
            selectinload(Request.topic),
        )
        .order_by(Request.responded_at.desc())
    )
    return list(await session.scalars(stmt))


async def interacted_user_ids(session: AsyncSession, user_id: int) -> set[int]:
    """ID пользователей, с которыми уже было принятое взаимодействие.

    Взаимодействие = есть заявка в статусе accepted или completed в любую
    сторону (я принял его заявку или он принял мою). Используется для плашки
    на доске «Вы уже взаимодействовали».
    """
    stmt = select(Request.sender_id, Request.receiver_id).where(
        or_(Request.sender_id == user_id, Request.receiver_id == user_id),
        Request.status.in_([RequestStatus.accepted, RequestStatus.completed]),
    )
    result = await session.execute(stmt)
    ids: set[int] = set()
    for sender_id, receiver_id in result.all():
        other = receiver_id if sender_id == user_id else sender_id
        ids.add(other)
    return ids


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
    начисляется здесь — только при завершении заявки отправителем
    (complete_by_sender) или решении админа в пользу объясняющего.
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
    # Первым сообщением чата отображаем текст заявки от отправителя. Текст уже
    # прошёл ensure_clean при создании заявки, поэтому вставляем Message напрямую
    # (минуя save_message, который мог бы бросить MutedError).
    if req.message:
        session.add(
            Message(
                chat_id=chat.id,
                sender_id=req.sender_id,
                body=req.message,
                source=MessageSource.web,
            )
        )
    req.status = RequestStatus.accepted
    req.chat_id = chat.id
    req.responded_at = datetime.now(timezone.utc)
    await session.flush()
    return req


async def _refund_if_chocolates(session: AsyncSession, req: Request) -> None:
    """Возвращает списанные шоколадки отправителю при отказе/отмене заявки.

    Сумма — цена, зафиксированная в заявке. При цене 0 (бесплатно) возвращать
    нечего.
    """
    if req.offer_type == OfferType.chocolates and req.price > 0:
        await chocolate_service.award(
            session,
            to_user_id=req.sender_id,
            amount=req.price,
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


async def _award_completion(session: AsyncSession, req: Request) -> None:
    """Завершает заявку в пользу объясняющего: статус completed, чат read-only,
    рейтинг и шоколадки объясняющему (receiver).

    Рейтинг: +1 за платное, +2 за бесплатное (price == 0). Шоколадки — только
    для оплаты шоколадками в размере зафиксированной цены; при цене 0 награды нет.
    """
    req.status = RequestStatus.completed
    req.completed_at = datetime.now(timezone.utc)
    req.cancel_requested = False
    req.cancel_disputed = False
    if req.chat_id is not None:
        await chat_service.complete_chat(session, req.chat_id)
    receiver = await session.get(User, req.receiver_id)
    if receiver is not None:
        receiver.rating += 2 if req.price == 0 else 1
    if req.offer_type == OfferType.chocolates and req.price > 0:
        await chocolate_service.award(
            session,
            to_user_id=req.receiver_id,
            amount=req.price,
            reason=ChocolateReason.explanation,
            from_user_id=req.sender_id,
            ref_type="request",
            ref_id=req.id,
        )


async def complete_by_sender(
    session: AsyncSession, request_id: int, user_id: int
) -> Request:
    """Завершение заявки отправителем (sender). Только отправитель может завершить.

    Заявка сразу → completed, объясняющему начисляются шоколадки и рейтинг.
    Недоступно, если по заявке идёт процесс отмены (cancel_requested/disputed).
    """
    req = await session.get(Request, request_id)
    if not req:
        raise RequestError("Заявка не найдена")
    if user_id != req.sender_id:
        raise RequestError("Завершить может только отправитель заявки")
    if req.status != RequestStatus.accepted:
        raise RequestError("Заявку нельзя завершить")
    if req.cancel_requested or req.cancel_disputed:
        raise RequestError("По заявке идёт процесс отмены")
    await _award_completion(session, req)
    await session.flush()
    return req


async def request_cancel(
    session: AsyncSession, request_id: int, user_id: int
) -> Request:
    """Отправитель (sender) запрашивает отмену объяснения.

    Ставит cancel_requested=True → ждём решения объясняющего (receiver).
    """
    req = await session.get(Request, request_id)
    if not req:
        raise RequestError("Заявка не найдена")
    if user_id != req.sender_id:
        raise RequestError("Отменить может только отправитель заявки")
    if req.status != RequestStatus.accepted:
        raise RequestError("Заявку нельзя отменить")
    if req.cancel_requested or req.cancel_disputed:
        raise RequestError("Отмена уже запрошена")
    req.cancel_requested = True
    await session.flush()
    return req


async def respond_cancel(
    session: AsyncSession, request_id: int, user_id: int, accept: bool
) -> Request:
    """Ответ объясняющего (receiver) на запрос отмены.

    accept=True → заявка cancelled, шоколадки возвращаются отправителю.
    accept=False → cancel_disputed=True, спор уходит админу на разбор.
    """
    req = await session.get(Request, request_id)
    if not req:
        raise RequestError("Заявка не найдена")
    if user_id != req.receiver_id:
        raise RequestError("Ответить на отмену может только объясняющий")
    if req.status != RequestStatus.accepted or not req.cancel_requested:
        raise RequestError("Нет запроса на отмену")
    if req.cancel_disputed:
        raise RequestError("Спор уже на рассмотрении админа")
    if accept:
        req.status = RequestStatus.cancelled
        req.cancel_requested = False
        req.responded_at = datetime.now(timezone.utc)
        if req.chat_id is not None:
            await chat_service.complete_chat(session, req.chat_id)
        await _refund_if_chocolates(session, req)
    else:
        req.cancel_disputed = True
    await session.flush()
    return req


async def admin_resolve_dispute(
    session: AsyncSession, request_id: int, cancel: bool
) -> Request:
    """Разбор спора об отмене админом.

    cancel=True → заявка cancelled, шоколадки возвращаются отправителю.
    cancel=False → заявка completed в пользу объясняющего (шоколадки + рейтинг).
    """
    req = await session.get(Request, request_id)
    if not req:
        raise RequestError("Заявка не найдена")
    if not req.cancel_disputed:
        raise RequestError("По заявке нет спора на рассмотрении")
    if cancel:
        req.status = RequestStatus.cancelled
        req.cancel_requested = False
        req.cancel_disputed = False
        req.responded_at = datetime.now(timezone.utc)
        if req.chat_id is not None:
            await chat_service.complete_chat(session, req.chat_id)
        await _refund_if_chocolates(session, req)
    else:
        await _award_completion(session, req)
    await session.flush()
    return req


async def list_disputed(session: AsyncSession) -> list[Request]:
    """Заявки со спором об отмене, ожидающие разбора админом."""
    result = await session.scalars(
        select(Request)
        .where(
            Request.status == RequestStatus.accepted,
            Request.cancel_disputed.is_(True),
        )
        .options(
            selectinload(Request.sender),
            selectinload(Request.receiver),
            selectinload(Request.topic),
        )
        .order_by(Request.responded_at.asc())
    )
    return list(result)


def _blocked_until(block: str) -> datetime | None:
    if block == "none":
        return None
    if block == "forever":
        return _FOREVER
    delta = _BLOCK_DURATIONS.get(block)
    if delta is None:
        return None
    return datetime.now(timezone.utc) + delta
