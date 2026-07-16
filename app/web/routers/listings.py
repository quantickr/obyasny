from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services import board_service
from app.web.dependencies import CurrentUserOptional, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/board", response_class=HTMLResponse)
async def board_page(
    request: Request,
    user: CurrentUserOptional,
    session: SessionDep,
    error: str = "",
    q: str = "",
):
    # Гостю — простой список без персонального метча; вошедшему — ранжирование.
    if user is None:
        cards = await board_service.list_board_cards_plain(session)
    else:
        cards = await board_service.list_board_cards_ranked(session, user.id)
    query = q.strip().lower()
    if query:
        # Фильтр по теме: оставляем карточки, где название темы (в любом из
        # списков «может объяснить» / «хочет узнать») содержит запрос.
        def matches(card):
            topics = card.can_teach + card.wants_learn
            return any(query in ut.topic.name.lower() for ut in topics)

        cards = [c for c in cards if matches(c)]
    return templates.TemplateResponse(
        request,
        "board.html",
        {"user": user, "cards": cards, "error": error, "q": q},
    )
