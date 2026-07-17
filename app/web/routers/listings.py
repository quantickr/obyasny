from fastapi import APIRouter, Query, Request
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
    university: list[str] = Query(default=[]),
):
    # Гостю — простой список без персонального метча; вошедшему — ранжирование.
    if user is None:
        cards = await board_service.list_board_cards_plain(session)
    else:
        cards = await board_service.list_board_cards_ranked(session, user.id)
    universities = await board_service.list_board_universities(session)
    # Мультифильтр по вузам: оставляем карточки студентов из выбранных вузов.
    selected = [u for u in (university or []) if u.strip()]
    if selected:
        chosen = set(selected)
        cards = [c for c in cards if (c.student.university or "") in chosen]
    query = q.strip().lower()
    if query:
        # Фильтр: оставляем карточки, где запрос содержится в названии темы
        # (в любом из списков «может объяснить» / «хочет узнать») ИЛИ в вузе.
        def matches(card):
            topics = card.can_teach + card.wants_learn
            if any(query in ut.topic.name.lower() for ut in topics):
                return True
            uni = card.student.university or ""
            return query in uni.lower()

        cards = [c for c in cards if matches(c)]
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            "user": user,
            "cards": cards,
            "error": error,
            "q": q,
            "universities": universities,
            "selected_universities": selected,
        },
    )
