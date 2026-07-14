import asyncio
from collections import defaultdict

from fastapi import WebSocket

from app.events import bus
from app.events.schemas import ChatEvent


class ConnectionManager:
    """Локальный реестр WS-подключений на процесс web + мост из Redis Pub/Sub.

    Один фоновый listener на chat_id рассылает события всем локальным сокетам.
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._listeners: dict[int, asyncio.Task] = {}

    async def connect(self, chat_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[chat_id].add(ws)
        if chat_id not in self._listeners:
            self._listeners[chat_id] = asyncio.create_task(
                self._listen(chat_id)
            )

    def disconnect(self, chat_id: int, ws: WebSocket) -> None:
        self._connections[chat_id].discard(ws)
        if not self._connections[chat_id]:
            self._connections.pop(chat_id, None)
            task = self._listeners.pop(chat_id, None)
            if task:
                task.cancel()

    async def _listen(self, chat_id: int) -> None:
        async for event in bus.subscribe_chat(chat_id):
            await self._broadcast_local(chat_id, event)

    async def _broadcast_local(self, chat_id: int, event: ChatEvent) -> None:
        payload = event.model_dump()
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(chat_id, ())):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(chat_id, ws)


manager = ConnectionManager()
