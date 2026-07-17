import re
from difflib import SequenceMatcher

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.data.topic_synonyms import TOPIC_SYNONYMS
from app.data.universities import UNIVERSITIES
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


def _build_synonym_index(
    groups: list[tuple[str, list[str]]],
) -> dict[str, set[str]]:
    """Строит индекс: нормализованный вариант → все связанные варианты.

    Так по любому из синонимов/алиасов (или полному названию) можно
    получить всю группу и расширить поисковый запрос.
    """
    index: dict[str, set[str]] = {}
    for canonical, aliases in groups:
        variants = {_norm(canonical)} | {_norm(a) for a in aliases}
        variants = {v for v in variants if v}
        for v in variants:
            index.setdefault(v, set()).update(variants)
    return index


# Индексы синонимов тем и алиасов вузов (строятся один раз при импорте).
_TOPIC_INDEX = _build_synonym_index(TOPIC_SYNONYMS)
_UNI_INDEX = _build_synonym_index(UNIVERSITIES)


def _expand_query(query: str) -> list[str]:
    """Расширяет запрос синонимами тем и алиасами вузов.

    Возвращает список вариантов для сравнения: сам запрос + все связанные
    формы (например «физтех» → «мфти», «московский физико-технический…»;
    «матан» → «математический анализ»). Ищем по всем.
    """
    q = _norm(query)
    variants: set[str] = {q} if q else set()
    for index in (_TOPIC_INDEX, _UNI_INDEX):
        if q in index:
            variants.update(index[q])
    return list(variants)


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
        # Расширяем запрос синонимами тем и алиасами вузов («физтех»→«мфти»,
        # «матан»→«математический анализ»), затем ищем нечётко (с опечатками).
        variants = _expand_query(query)

        def matches(card):
            topics = card.can_teach + card.wants_learn
            for ut in topics:
                if any(_fuzzy_hit(v, ut.topic.name) for v in variants):
                    return True
            uni = card.student.university or ""
            return any(_fuzzy_hit(v, uni) for v in variants)

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
