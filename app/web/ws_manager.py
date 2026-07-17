import asyncio
from collections import defaultdict

from fastapi import WebSocket

from app.core.database import async_session_factory
from app.events import bus
from app.events.schemas import ChatEvent
from app.services import chat_service


class ConnectionManager:
    """Локальный реестр WS-подключений на процесс web + мост из Redis Pub/Sub.

    Один фоновый listener на chat_id рассылает события всем локальным сокетам.
    Для каждого сокета хранится user_id: при доставке входящего сообщения
    в открытый чат оно сразу помечается прочитанным.

    Пока сокет чата открыт, в Redis держится ключ presence (см. bus), который
    периодически продлевается heartbeat-задачей. Бот по этому ключу понимает,
    что получатель смотрит чат на сайте, и не шлёт уведомление в Telegram.
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._user_of: dict[WebSocket, int] = {}
        self._listeners: dict[int, asyncio.Task] = {}
        self._heartbeats: dict[WebSocket, asyncio.Task] = {}

    async def connect(
        self, chat_id: int, ws: WebSocket, user_id: int
    ) -> None:
        await ws.accept()
        self._connections[chat_id].add(ws)
        self._user_of[ws] = user_id
        # Сразу отмечаем присутствие и запускаем продление ключа.
        await bus.mark_present(chat_id, user_id)
        self._heartbeats[ws] = asyncio.create_task(
            self._heartbeat(chat_id, user_id, ws)
        )
        if chat_id not in self._listeners:
            self._listeners[chat_id] = asyncio.create_task(
                self._listen(chat_id)
            )

    def disconnect(self, chat_id: int, ws: WebSocket) -> None:
        self._connections[chat_id].discard(ws)
        user_id = self._user_of.pop(ws, None)
        hb = self._heartbeats.pop(ws, None)
        if hb:
            hb.cancel()
        if user_id is not None:
            # Снимаем присутствие (не блокируя disconnect на await).
            asyncio.create_task(bus.clear_present(chat_id, user_id))
        if not self._connections[chat_id]:
            self._connections.pop(chat_id, None)
            task = self._listeners.pop(chat_id, None)
            if task:
                task.cancel()

    async def _heartbeat(
        self, chat_id: int, user_id: int, ws: WebSocket
    ) -> None:
        """Продлевает presence-ключ, пока сокет открыт."""
        try:
            while True:
                await asyncio.sleep(10)
                if ws not in self._user_of:
                    return
                await bus.mark_present(chat_id, user_id)
        except asyncio.CancelledError:
            return

    async def _listen(self, chat_id: int) -> None:
        async for event in bus.subscribe_chat(chat_id):
            await self._broadcast_local(chat_id, event)

    async def _broadcast_local(self, chat_id: int, event: ChatEvent) -> None:
        payload = event.model_dump()
        dead: list[WebSocket] = []
        # Получатели, реально смотрящие открытый чат (не автор сообщения).
        viewers: set[int] = set()
        for ws in list(self._connections.get(chat_id, ())):
            try:
                await ws.send_json(payload)
                uid = self._user_of.get(ws)
                if uid is not None and uid != event.sender_id:
                    viewers.add(uid)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(chat_id, ws)
        # Сразу помечаем доставленное прочитанным для присутствующих зрителей.
        for uid in viewers:
            async with async_session_factory() as session:
                await chat_service.mark_chat_read(session, chat_id, uid)
                await session.commit()


manager = ConnectionManager()
