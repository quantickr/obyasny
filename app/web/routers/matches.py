from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/matches")
async def matches_page():
    """Вкладка «Пары» удалена — доска теперь персонально ранжирована."""
    return RedirectResponse(url="/board", status_code=301)
