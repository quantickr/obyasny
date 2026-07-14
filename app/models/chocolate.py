from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ChocolateReason(str, enum.Enum):
    explanation = "explanation"
    bonus = "bonus"
    signup = "signup"
    manual = "manual"


class ChocolateTransaction(Base, TimestampMixin):
    """Журнал благодарности — источник истины для баланса шоколадок."""

    __tablename__ = "chocolate_transactions"
    __table_args__ = (
        Index("ix_chocolate_to_created", "to_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # NULL = системное начисление
    from_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    to_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[ChocolateReason] = mapped_column(
        Enum(ChocolateReason, name="chocolate_reason"), nullable=False
    )
    ref_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
