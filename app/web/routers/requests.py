from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services import request_service
from app.services.request_service import RequestError
from app.web.dependencies import CurrentUser, SessionDep
from app.web.templating import templates

router = APIRouter()


@router.get("/requests", response_class=HTMLResponse)
async def requests_page(
    request: Request, user: CurrentUser, session: SessionDep, tab: str = "incoming"
):
    incoming = await request_service.incoming(session, user.id)
    outgoing = await request_service.outgoing(session, user.id)
    active = await request_service.active(session, user.id)
    completed = await request_service.completed(session, user.id)
    return templates.TemplateResponse(
        request,
        "requests.html",
        {
            "user": user,
            "incoming": incoming,
            "outgoing": outgoing,
            "active": active,
            "completed": completed,
            "tab": tab,
        },
    )


@router.post("/requests/{request_id}/accept")
async def accept(request_id: int, user: CurrentUser, session: SessionDep):
    try:
        req = await request_service.accept_request(session, request_id, user.id)
        await session.commit()
        if req.chat_id:
            return RedirectResponse(
                url=f"/chat/{req.chat_id}", status_code=303
            )
    except RequestError:
        pass
    return RedirectResponse(url="/requests", status_code=303)


@router.post("/requests/{request_id}/decline")
async def decline(
    request_id: int,
    user: CurrentUser,
    session: SessionDep,
    block: str = Form("forever"),
):
    try:
        await request_service.decline_request(
            session, request_id, user.id, block=block
        )
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url="/requests", status_code=303)


@router.post("/requests/{request_id}/done")
async def mark_done(request_id: int, user: CurrentUser, session: SessionDep):
    """Отметить «Завершить». Задача закрывается по обоюдному согласию сторон."""
    try:
        await request_service.toggle_done(session, request_id, user.id)
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url="/requests?tab=active", status_code=303)


@router.post("/requests/{request_id}/decline-all")
async def decline_all(
    request_id: int,
    user: CurrentUser,
    session: SessionDep,
    block: str = Form("forever"),
):
    try:
        await request_service.decline_all_from(
            session, request_id, user.id, block=block
        )
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url="/requests", status_code=303)
