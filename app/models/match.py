from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class MatchStatus(str, enum.Enum):
    suggested = "suggested"
    a_accepted = "a_accepted"
    b_accepted = "b_accepted"
    confirmed = "confirmed"
    rejected = "rejected"
    expired = "expired"


class Match(Base, TimestampMixin):
    """Авто-подобранная взаимовыгодная пара. Инвариант: user_a_id < user_b_id."""

    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("user_a_id < user_b_id", name="ck_match_user_order"),
        UniqueConstraint(
            "user_a_id",
            "user_b_id",
            "a_teaches_topic_id",
            "b_teaches_topic_id",
            name="uq_match_pair_topics",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    a_teaches_topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    b_teaches_topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Numeric(6, 2), default=0, nullable=False)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status"),
        default=MatchStatus.suggested,
        nullable=False,
    )
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True
    )
