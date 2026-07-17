import re
from difflib import SequenceMatcher

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.services import board_service
from app.web.dependencies import CurrentUserOptional, SessionDep
from app.web.templating import templates

router = APIRouter()

# Порог нечёткого совпадения (0..1): ловит опечатки, но отсекает случайное.
_FUZZY_THRESHOLD = 0.7


def _norm(text: str) -> str:
    """Нижний регистр, ё→е, схлопывание не-буквенно-цифровых в пробел."""
    s = text.lower().replace("ё", "е")
    s = re.sub(r"[^0-9a-zа-я]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _fuzzy_hit(query: str, text: str) -> bool:
    """Совпадает ли запрос с текстом с учётом опечаток.

    Сначала — обычное вхождение подстроки (быстро, точно). Затем —
    нечёткое сравнение запроса с каждым словом текста (ловит «матиматика»
    → «математика»), а для коротких запросов — со всем текстом целиком.
    """
    q = _norm(query)
    t = _norm(text)
    if not q or not t:
        return False
    if q in t:
        return True
    for word in t.split():
        # Сравниваем слова близкой длины, чтобы не ловить ложные совпадения.
        if abs(len(word) - len(q)) <= max(3, len(q) // 2):
            if SequenceMatcher(None, q, word).ratio() >= _FUZZY_THRESHOLD:
                return True
    # Короткий запрос — пробуем совпасть с началом текста целиком.
    if len(q) >= 4 and SequenceMatcher(None, q, t[: len(q) + 3]).ratio() >= _FUZZY_THRESHOLD:
        return True
    return False


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
    query = q.strip()
    if query:
        # Фильтр с устойчивостью к опечаткам: карточка подходит, если запрос
        # нечётко совпадает с названием темы (в любом из списков «может
        # объяснить» / «хочет узнать») ИЛИ с названием вуза.
        def matches(card):
            topics = card.can_teach + card.wants_learn
            if any(_fuzzy_hit(query, ut.topic.name) for ut in topics):
                return True
            return _fuzzy_hit(query, card.student.university or "")

        cards = [c for c in cards if matches(c)]
    # AJAX-запрос (живой поиск) — отдаём только фрагмент с карточками.
    is_ajax = request.headers.get("x-requested-with") == "fetch"
    template = "board_results.html" if is_ajax else "board.html"
    return templates.TemplateResponse(
        request,
        template,
        {
            "user": user,
            "cards": cards,
            "error": error,
            "q": q,
            "universities": universities,
            "selected_universities": selected,
        },
    )
