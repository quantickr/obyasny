from fastapi import APIRouter, Form
from fastapi.responses import RedirectResponse

from app.models.chat import ChatContext
from app.services import chat_service
from app.web.dependencies import CurrentUser, SessionDep

router = APIRouter()


@router.get("/matches")
async def matches_page():
    """Вкладка «Пары» удалена — доска теперь персонально ранжирована."""
    return RedirectResponse(url="/board", status_code=301)


@router.post("/matches/connect")
async def connect_match(
    user: CurrentUser,
    session: SessionDep,
    partner_id: int = Form(...),
):
    """Совместимость со старыми ссылками: создаём чат и ведём в него."""
    if partner_id == user.id:
        return RedirectResponse(url="/board", status_code=303)
    chat = await chat_service.get_or_create_chat(
        session, user.id, partner_id, context_type=ChatContext.match
    )
    await session.commit()
    return RedirectResponse(url=f"/chat/{chat.id}", status_code=303)
