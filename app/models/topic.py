from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class TopicKind(str, enum.Enum):
    can_teach = "can_teach"
    wants_learn = "wants_learn"


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)


class UserTopic(Base, TimestampMixin):
    """Сердце матчинга: кто что умеет объяснить / что хочет узнать."""

    __tablename__ = "user_topics"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", "kind", name="uq_user_topic_kind"),
        Index("ix_user_topics_topic_kind", "topic_id", "kind"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[TopicKind] = mapped_column(
        Enum(TopicKind, name="topic_kind"), nullable=False
    )
    level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # Что именно непонятно (только для kind == wants_learn)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Цена в шоколадках за объяснение (только для kind == can_teach).
    # None → цена не задана (трактуется как 1). Диапазон 1..3.
    price: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    user: Mapped["User"] = relationship(back_populates="user_topics")
    topic: Mapped["Topic"] = relationship()
