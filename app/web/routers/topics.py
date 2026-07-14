from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import board_service
from app.web.dependencies import CurrentUser, SessionDep

router = APIRouter()


@router.get("/api/topics/suggest")
async def suggest_topics(
    user: CurrentUser, session: SessionDep, q: str = ""
):
    """Подсказки тем с доски для автодополнения (JSON-массив строк)."""
    names = await board_service.board_topic_names(session, q=q, limit=10)
    return JSONResponse(names)
