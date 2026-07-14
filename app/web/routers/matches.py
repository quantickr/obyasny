from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.chat import ChatContext
from app.services import chat_service, match_service, request_service
from app.services.request_service import RequestError
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/matches", response_class=HTMLResponse)
async def matches_page(request: Request, user: CurrentUser, session: SessionDep):
    candidates = await match_service.find_mutual_matches(session, user.id)
    return templates.TemplateResponse(
        request,
        "matches.html",
        {"user": user, "candidates": candidates},
    )


@router.post("/matches/connect")
async def connect_match(
    user: CurrentUser,
    session: SessionDep,
    partner_id: int = Form(...),
):
    """Начать общение с подобранной парой: создаём чат напрямую."""
    if partner_id == user.id:
        return RedirectResponse(url="/matches", status_code=303)
    chat = await chat_service.get_or_create_chat(
        session, user.id, partner_id, context_type=ChatContext.match
    )
    await session.commit()
    return RedirectResponse(url=f"/chat/{chat.id}", status_code=303)
