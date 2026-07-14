from pydantic import BaseModel


class ChatEvent(BaseModel):
    """Событие нового сообщения, публикуемое в Redis Pub/Sub."""

    chat_id: int
    message_id: int
    sender_id: int
    body: str
    source: str  # 'web' | 'telegram'
    tg_message_id: int | None = None
    created_at: str
