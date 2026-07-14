from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.models.topic import TopicKind
from app.services import board_service
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/board", response_class=HTMLResponse)
async def board_page(request: Request, user: CurrentUser, session: SessionDep):
    board_users = await board_service.list_board_users(session)
    cards = []
    for u in board_users:
        can_teach = [
            ut for ut in u.user_topics if ut.kind == TopicKind.can_teach
        ]
        wants_learn = [
            ut for ut in u.user_topics if ut.kind == TopicKind.wants_learn
        ]
        cards.append(
            {"student": u, "can_teach": can_teach, "wants_learn": wants_learn}
        )
    return templates.TemplateResponse(
        request,
        "board.html",
        {"user": user, "cards": cards},
    )
