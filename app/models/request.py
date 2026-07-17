from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.topic import Topic
    from app.models.user import User


class OfferType(str, enum.Enum):
    exchange = "exchange"
    chocolates = "chocolates"


class RequestStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    cancelled = "cancelled"
    completed = "completed"


class Request(Base, TimestampMixin):
    """Заявка: 'объясни мне тему X, взамен — обмен темой или шоколадки'."""

    __tablename__ = "requests"
    __table_args__ = (
        Index("ix_requests_receiver_status", "receiver_id", "status"),
        Index("ix_requests_sender_status", "sender_id", "status"),
        Index("ix_requests_pair_status", "sender_id", "receiver_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sender_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    receiver_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    offer_type: Mapped[OfferType] = mapped_column(
        Enum(OfferType, name="offer_type"),
        default=OfferType.chocolates,
        nullable=False,
    )
    offer_topic_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status"),
        default=RequestStatus.pending,
        nullable=False,
    )
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    blocked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Завершение по обоюдному согласию: обе стороны жмут «Завершить».
    # Когда оба флага True → status=completed, объясняющему +1 шоколадка.
    sender_done: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    receiver_done: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])
    receiver: Mapped["User"] = relationship(foreign_keys=[receiver_id])
    topic: Mapped["Topic"] = relationship(foreign_keys=[topic_id])
