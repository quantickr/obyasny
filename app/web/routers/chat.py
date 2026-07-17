import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.core.database import async_session_factory
from app.core.security import decode_session_token
from app.events import bus
from app.events.schemas import ChatEvent
from app.models.chat import MessageSource
from app.services import (
    chat_service,
    chocolate_service,
    request_service,
    user_service,
)
from app.services.request_service import RequestError
from app.web.dependencies import (
    SESSION_COOKIE,
    CurrentUser,
    CurrentUserOptional,
    SessionDep,
)
from app.web.templating import templates
from app.web.ws_manager import manager

router = APIRouter()
logger = logging.getLogger(__name__)


async def _chat_sidebar(session, user, active_chat_id=None):
    """Собирает данные для боковой панели чатов: собеседники, непрочитанные,
    превью последнего сообщения. Возвращает список чатов и словари."""
    chats = await chat_service.list_user_chats(session, user.id)
    partners = {}
    for c in chats:
        pid = chat_service.other_participant(c, user.id)
        partners[c.id] = await user_service.get_by_id(session, pid)
    unread = await chat_service.unread_by_chat(session, user.id)
    last = await chat_service.last_message_by_chat(
        session, [c.id for c in chats]
    )
    return chats, partners, unread, last


@router.get("/api/unread")
async def api_unread(user: CurrentUserOptional, session: SessionDep):
    """Счётчики для навигации: непрочитанные сообщения, входящие заявки,
    баланс шоколадок (для уведомлений о начислении/трате на клиенте)."""
    if user is None:
        return JSONResponse({"messages": 0, "requests": 0, "chocolates": 0})
    messages = await chat_service.unread_total(session, user.id)
    requests_n = await request_service.incoming_count(session, user.id)
    chocolates = await chocolate_service.get_balance(session, user.id)
    return JSONResponse(
        {
            "messages": messages,
            "requests": requests_n,
            "chocolates": chocolates,
        }
    )


@router.get("/chats", response_class=HTMLResponse)
async def chats_list(request: Request, user: CurrentUser, session: SessionDep):
    chats, partners, unread, last = await _chat_sidebar(session, user)
    # Сразу открываем самый свежий чат: сперва чаты с сообщениями (по времени
    # последнего), затем — без сообщений (по id). Пустой список — заглушка.
    if chats:
        with_msg = [c for c in chats if c.id in last]
        if with_msg:
            newest = max(with_msg, key=lambda c: last[c.id].created_at)
        else:
            newest = max(chats, key=lambda c: c.id)
        return RedirectResponse(url=f"/chat/{newest.id}", status_code=303)
    return templates.TemplateResponse(
        request,
        "chats.html",
        {
            "user": user,
            "chats": chats,
            "partners": partners,
            "unread": unread,
            "last": last,
        },
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
    # Открытие чата помечает входящие сообщения прочитанными.
    await chat_service.mark_chat_read(session, chat_id, user.id)
    await session.commit()

    # Связанная заявка (если чат создан из заявки) — для кнопки «Завершить».
    req = None
    my_done = False
    partner_done = False
    if chat.context_id is not None:
        req = await request_service.get_request(session, chat.context_id)
        if req is not None:
            my_done = (
                req.sender_done if user.id == req.sender_id else req.receiver_done
            )
            partner_done = (
                req.receiver_done if user.id == req.sender_id else req.sender_done
            )

    blocked = await chat_service.is_blocked(session, user.id, partner_id)

    chats, partners, unread, last = await _chat_sidebar(session, user)
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "user": user,
            "chat": chat,
            "partner": partner,
            "messages": messages,
            "chats": chats,
            "partners": partners,
            "unread": unread,
            "last": last,
            "req": req,
            "my_done": my_done,
            "partner_done": partner_done,
            "completed": chat.completed_at is not None,
            "blocked": blocked,
        },
    )


@router.post("/chat/{chat_id}/done")
async def chat_done(chat_id: int, user: CurrentUser, session: SessionDep):
    """Кнопка «Завершить» в окне чата → завершение по обоюдному согласию."""
    chat = await chat_service.get_chat_for_user(session, chat_id, user.id)
    if chat is None or chat.context_id is None:
        return RedirectResponse(url=f"/chat/{chat_id}", status_code=303)
    try:
        await request_service.toggle_done(session, chat.context_id, user.id)
        await session.commit()
    except RequestError:
        pass
    return RedirectResponse(url=f"/chat/{chat_id}", status_code=303)


@router.post("/chat/{chat_id}/hide")
async def chat_hide(chat_id: int, user: CurrentUser, session: SessionDep):
    """«Удалить» завершённый чат = скрыть только у себя."""
    await chat_service.hide_chat(session, chat_id, user.id)
    await session.commit()
    return RedirectResponse(url="/chats", status_code=303)


@router.post("/chat/{chat_id}/block")
async def chat_block(chat_id: int, user: CurrentUser, session: SessionDep):
    """Заблокировать собеседника «для себя»: чат прячется, TG-уведомления гаснут."""
    chat = await chat_service.get_chat_for_user(session, chat_id, user.id)
    if chat is not None:
        partner_id = chat_service.other_participant(chat, user.id)
        await chat_service.block_user(session, user.id, partner_id)
        await session.commit()
    return RedirectResponse(url="/chats", status_code=303)


@router.post("/chat/{chat_id}/unblock")
async def chat_unblock(chat_id: int, user: CurrentUser, session: SessionDep):
    """Разблокировать собеседника."""
    chat = await chat_service.get_chat_for_user(session, chat_id, user.id)
    if chat is not None:
        partner_id = chat_service.other_participant(chat, user.id)
        await chat_service.unblock_user(session, user.id, partner_id)
        await session.commit()
    return RedirectResponse(url=f"/chat/{chat_id}", status_code=303)


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

    await manager.connect(chat_id, websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            body = (data.get("body") or "").strip()
            if not body:
                continue
            async with async_session_factory() as session:
                # В завершённый чат писать нельзя (read-only).
                chat = await chat_service.get_chat_for_user(
                    session, chat_id, user_id
                )
                if chat is None or chat.completed_at is not None:
                    continue
                try:
                    msg = await chat_service.save_message(
                        session,
                        chat_id=chat_id,
                        sender_id=user_id,
                        body=body,
                        source=MessageSource.web,
                    )
                except chat_service.MutedError:
                    # Пользователь замучен админом — сообщение не сохраняем.
                    try:
                        await websocket.send_json({"error": "muted"})
                    except Exception:
                        pass
                    continue
                # Снимаем поля до commit: после него объект может быть expired.
                msg_id = msg.id
                clean_body = msg.body  # цензурированная версия из save_message
                created_at = msg.created_at.isoformat()
                await session.commit()
                event = ChatEvent(
                    chat_id=chat_id,
                    message_id=msg_id,
                    sender_id=user_id,
                    body=clean_body,
                    source="web",
                    created_at=created_at,
                )
            # Публикуем в шину: web-listener разошлёт по WS, bot доставит в TG.
            await bus.publish_message(event)
    except WebSocketDisconnect:
        manager.disconnect(chat_id, websocket)
    except Exception:
        # Непредвиденная ошибка в цикле WS — логируем со стек-трейсом,
        # чтобы не терять диагностику, и корректно отключаем сокет.
        logger.exception(
            "Ошибка в WebSocket чата chat_id=%s user_id=%s", chat_id, user_id
        )
        manager.disconnect(chat_id, websocket)
