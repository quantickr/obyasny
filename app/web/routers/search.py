from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.models.request import OfferType
from app.services import request_service, user_service
from app.services.request_service import RequestError
from app.web.dependencies import CurrentUser, SessionDep

router = APIRouter()


@router.get("/search")
async def search_page(q: str = ""):
    """Поиск переехал на доску. Прокидываем запрос в /board через редирект."""
    if q.strip():
        return RedirectResponse(url=f"/board?q={quote(q)}", status_code=303)
    return RedirectResponse(url="/board", status_code=303)


@router.post("/search/request")
async def send_request(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    receiver_id: int = Form(...),
    topic_id: int = Form(...),
    message: str = Form(""),
    offer_type: str = Form("chocolates"),
    next_url: str = Form("/board"),
):
    is_ajax = request.headers.get("x-requested-with") == "fetch"
    receiver = await user_service.get_by_id(session, receiver_id)
    if receiver is None:
        if is_ajax:
            return JSONResponse(
                {"ok": False, "error": "Пользователь не найден"}, status_code=404
            )
        return RedirectResponse(url="/board", status_code=303)
    try:
        await request_service.create_request(
            session,
            sender_id=user.id,
            receiver_id=receiver_id,
            topic_id=topic_id,
            message=message or None,
            offer_type=OfferType(offer_type),
        )
        await session.commit()
    except RequestError as e:
        if is_ajax:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        sep = "&" if "?" in next_url else "?"
        return RedirectResponse(
            url=f"{next_url}{sep}error={quote(str(e))}", status_code=303
        )
    if is_ajax:
        return JSONResponse({"ok": True})
    return RedirectResponse(url="/requests?tab=outgoing", status_code=303)
