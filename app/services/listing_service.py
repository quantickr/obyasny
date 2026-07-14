from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.listing import (
    Listing,
    ListingResponse,
    ListingStatus,
    ResponseStatus,
)


class ListingError(Exception):
    pass


async def create_listing(
    session: AsyncSession,
    author_id: int,
    teach_topic_id: int | None,
    learn_topic_id: int | None,
    description: str | None,
) -> Listing:
    if teach_topic_id is None and learn_topic_id is None:
        raise ListingError("Укажите хотя бы одну тему")
    listing = Listing(
        author_id=author_id,
        teach_topic_id=teach_topic_id,
        learn_topic_id=learn_topic_id,
        description=description,
        status=ListingStatus.open,
    )
    session.add(listing)
    await session.flush()
    return listing


async def list_open(
    session: AsyncSession, limit: int = 50
) -> list[Listing]:
    stmt = (
        select(Listing)
        .where(Listing.status == ListingStatus.open)
        .order_by(Listing.created_at.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def get_listing(session: AsyncSession, listing_id: int) -> Listing | None:
    return await session.get(Listing, listing_id)


async def respond(
    session: AsyncSession,
    listing_id: int,
    responder_id: int,
    message: str | None = None,
) -> ListingResponse:
    listing = await session.get(Listing, listing_id)
    if not listing or listing.status != ListingStatus.open:
        raise ListingError("Объявление недоступно")
    if listing.author_id == responder_id:
        raise ListingError("Нельзя откликнуться на своё объявление")

    existing = await session.scalar(
        select(ListingResponse).where(
            ListingResponse.listing_id == listing_id,
            ListingResponse.responder_id == responder_id,
        )
    )
    if existing:
        raise ListingError("Вы уже откликнулись")

    resp = ListingResponse(
        listing_id=listing_id,
        responder_id=responder_id,
        message=message,
        status=ResponseStatus.pending,
    )
    session.add(resp)
    await session.flush()
    return resp
