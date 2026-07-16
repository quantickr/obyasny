from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models.request import OfferType
from app.services import request_service, search_service, user_service
from app.services.request_service import RequestError
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    q: str = "",
    error: str = "",
):
    results = []
    if q:
        results = await search_service.find_teachers_by_query(
            session, q, exclude_user_id=user.id
        )
    return templates.TemplateResponse(
        request,
        "search.html",
        {"user": user, "q": q, "results": results, "error": error},
    )


@router.post("/search/request")
async def send_request(
    user: CurrentUser,
    session: SessionDep,
    receiver_id: int = Form(...),
    topic_id: int = Form(...),
    message: str = Form(""),
    offer_type: str = Form("chocolates"),
    next_url: str = Form("/board"),
):
    receiver = await user_service.get_by_id(session, receiver_id)
    if receiver is None:
        return RedirectResponse(url="/search", status_code=303)
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
        sep = "&" if "?" in next_url else "?"
        return RedirectResponse(
            url=f"{next_url}{sep}error={quote(str(e))}", status_code=303
        )
    return RedirectResponse(url="/requests?tab=outgoing", status_code=303)
