from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.database import async_session_factory
from app.core.security import decode_session_token
from app.events import bus
from app.events.schemas import ChatEvent
from app.models.chat import MessageSource
from app.services import chat_service, user_service
from app.web.dependencies import SESSION_COOKIE, CurrentUser, SessionDep
from app.web.templating import templates
from app.web.ws_manager import manager

router = APIRouter()


@router.get("/chats", response_class=HTMLResponse)
async def chats_list(request: Request, user: CurrentUser, session: SessionDep):
    chats = await chat_service.list_user_chats(session, user.id)
    partners = {}
    for c in chats:
        pid = chat_service.other_participant(c, user.id)
        partners[c.id] = await user_service.get_by_id(session, pid)
    return templates.TemplateResponse(
        request,
        "chats.html",
        {"user": user, "chats": chats, "partners": partners},
    )


@router.get("/chat/{chat_id}", response_class=HTMLResponse)
async def chat_page(
    request: Request, chat_id: int, user: CurrentUser, session: SessionDep
):
    chat = await chat_service.get_chat_for_user(session, chat_id, user.id)
    if chat is None:
        return RedirectResponse(url="/chats", status_code=303)
    partner_id = chat_service.other_participant(chat, user.id)
    partner = await user_service.get_by_id(session, partner_id)
    messages = await chat_service.get_messages(session, chat_id)
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "user": user,
            "chat": chat,
            "partner": partner,
            "messages": messages,
        },
    )


@router.websocket("/ws/chat/{chat_id}")
async def chat_ws(websocket: WebSocket, chat_id: int):
    # Аутентификация по session-cookie (WS не проходит через обычные Depends).
    token = websocket.cookies.get(SESSION_COOKIE)
    user_id = decode_session_token(token) if token else None
    if user_id is None:
        await websocket.close(code=1008)
        return

    async with async_session_factory() as session:
        chat = await chat_service.get_chat_for_user(session, chat_id, user_id)
        if chat is None:
            await websocket.close(code=1008)
            return

    await manager.connect(chat_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            body = (data.get("body") or "").strip()
            if not body:
                continue
            async with async_session_factory() as session:
                msg = await chat_service.save_message(
                    session,
                    chat_id=chat_id,
                    sender_id=user_id,
                    body=body,
                    source=MessageSource.web,
                )
                await session.commit()
                event = ChatEvent(
                    chat_id=chat_id,
                    message_id=msg.id,
                    sender_id=user_id,
                    body=body,
                    source="web",
                    created_at=msg.created_at.isoformat(),
                )
            # Публикуем в шину: web-listener разошлёт по WS, bot доставит в TG.
            await bus.publish_message(event)
    except WebSocketDisconnect:
        manager.disconnect(chat_id, websocket)
    except Exception:
        manager.disconnect(chat_id, websocket)
