from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import listing_service, topic_service
from app.services.listing_service import ListingError
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/board", response_class=HTMLResponse)
async def board_page(request: Request, user: CurrentUser, session: SessionDep):
    listings = await listing_service.list_open(session)
    # Подтягиваем темы для отображения
    from app.models.topic import Topic

    topic_ids = set()
    for l in listings:
        if l.teach_topic_id:
            topic_ids.add(l.teach_topic_id)
        if l.learn_topic_id:
            topic_ids.add(l.learn_topic_id)
    topics = {}
    if topic_ids:
        from sqlalchemy import select

        for t in await session.scalars(select(Topic).where(Topic.id.in_(topic_ids))):
            topics[t.id] = t
    return templates.TemplateResponse(
        request,
        "board.html",
        {"user": user, "listings": listings, "topics": topics},
    )


@router.post("/board/create")
async def create_listing(
    user: CurrentUser,
    session: SessionDep,
    teach_topic: str = Form(""),
    learn_topic: str = Form(""),
    description: str = Form(""),
):
    teach_id = None
    learn_id = None
    if teach_topic.strip():
        teach_id = (
            await topic_service.get_or_create_topic(session, teach_topic)
        ).id
    if learn_topic.strip():
        learn_id = (
            await topic_service.get_or_create_topic(session, learn_topic)
        ).id
    try:
        await listing_service.create_listing(
            session, user.id, teach_id, learn_id, description or None
        )
        await session.commit()
    except ListingError:
        pass
    return RedirectResponse(url="/board", status_code=303)


@router.post("/board/{listing_id}/respond")
async def respond_listing(
    listing_id: int,
    user: CurrentUser,
    session: SessionDep,
    message: str = Form(""),
):
    try:
        await listing_service.respond(session, listing_id, user.id, message or None)
        await session.commit()
    except ListingError:
        pass
    return RedirectResponse(url="/board", status_code=303)
