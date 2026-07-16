from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.chat import ChatContext
from app.services import board_service, chat_service
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/board", response_class=HTMLResponse)
async def board_page(
    request: Request, user: CurrentUser, session: SessionDep, error: str = ""
):
    cards = await board_service.list_board_cards_ranked(session, user.id)
    return templates.TemplateResponse(
        request,
        "board.html",
        {"user": user, "cards": cards, "error": error},
    )


@router.post("/board/connect")
async def board_connect(
    user: CurrentUser,
    session: SessionDep,
    partner_id: int = Form(...),
):
    """Начать общение с подобранной парой напрямую (без заявки)."""
    if partner_id == user.id:
        return RedirectResponse(url="/board", status_code=303)
    chat = await chat_service.get_or_create_chat(
        session, user.id, partner_id, context_type=ChatContext.match
    )
    await session.commit()
    return RedirectResponse(url=f"/chat/{chat.id}", status_code=303)
