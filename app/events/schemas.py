from pydantic import BaseModel


class ChatEvent(BaseModel):
    """Событие нового сообщения, публикуемое в Redis Pub/Sub."""

    chat_id: int
    message_id: int
    sender_id: int
    body: str
    source: str  # 'web' | 'telegram'
    tg_message_id: int | None = None
    reply_to_id: int | None = None
    reply_preview: str | None = None  # усечённый текст цитируемого сообщения
    created_at: str
