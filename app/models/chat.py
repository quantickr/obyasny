from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class ChatContext(str, enum.Enum):
    request = "request"
    listing = "listing"
    match = "match"
    direct = "direct"


class MessageSource(str, enum.Enum):
    web = "web"
    telegram = "telegram"


class Chat(Base, TimestampMixin):
    __tablename__ = "chats"
    # UNIQUE-ограничения на пару юзеров нет: на каждую принятую заявку
    # создаётся отдельный чат (заголовок = «Тема + Имя»).

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user1_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user2_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    context_type: Mapped[ChatContext | None] = mapped_column(
        Enum(ChatContext, name="chat_context"), nullable=True
    )
    context_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Заголовок чата = «Тема + Имя собеседника» (заполняется при создании чата
    # из заявки). Для старых/direct-чатов может быть NULL.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Задача завершена по обоюдному согласию: чат read-only, серый, уходит вниз.
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # «Удаление» завершённого чата = скрытие только у себя (у собеседника остаётся).
    hidden_user1: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    hidden_user2: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_chat_created", "chat_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    chat_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[MessageSource] = mapped_column(
        Enum(MessageSource, name="message_source"), nullable=False
    )
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reply_to_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    reply_to: Mapped["Message | None"] = relationship(
        "Message", remote_side="Message.id", lazy="joined"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
