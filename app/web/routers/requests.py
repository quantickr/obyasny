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


@router.post("/requests/{request_id}/complete")
async def complete(request_id: int, user: CurrentUser, session: SessionDep):
    """Завершить заявку. Доступно только отправителю (sender): заявка сразу
    закрывается, объясняющему начисляются шоколадки и рейтинг."""
    try:
        await request_service.complete_by_sender(session, request_id, user.id)
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url="/requests?tab=active", status_code=303)


@router.post("/requests/{request_id}/cancel")
async def cancel(request_id: int, user: CurrentUser, session: SessionDep):
    """Отправитель (sender) просит отменить объяснение → на подтверждение
    объясняющему."""
    try:
        await request_service.request_cancel(session, request_id, user.id)
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url="/requests?tab=active", status_code=303)


@router.post("/requests/{request_id}/cancel-response")
async def cancel_response(
    request_id: int,
    user: CurrentUser,
    session: SessionDep,
    accept: str = Form("no"),
):
    """Ответ объясняющего (receiver) на запрос отмены: accept=yes → отмена
    (возврат шоколадок), accept=no → спор уходит админу."""
    try:
        await request_service.respond_cancel(
            session, request_id, user.id, accept=(accept == "yes")
        )
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
