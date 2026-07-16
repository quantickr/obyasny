from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import university_service

router = APIRouter()


@router.get("/api/universities/suggest")
async def suggest_universities(q: str = ""):
    """Подсказки вузов для автодополнения (JSON-массив строк).

    Публичный: нужен и на форме регистрации (пользователь ещё не залогинен).
    """
    return JSONResponse(university_service.suggest(q, limit=10))
