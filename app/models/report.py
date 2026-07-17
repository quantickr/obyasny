from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ReportStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class ReportContext(str, enum.Enum):
    board = "board"      # жалоба с доски
    profile = "profile"  # жалоба с публичного профиля
    chat = "chat"        # жалоба на собеседника в чате


class Report(Base, TimestampMixin):
    """Жалоба одного пользователя на другого. Разбирает админ в /admin."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    reporter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reported_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    context: Mapped[ReportContext] = mapped_column(
        Enum(ReportContext, name="report_context"),
        default=ReportContext.board,
        nullable=False,
    )
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chats.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="report_status"),
        default=ReportStatus.open,
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    reporter: Mapped["User"] = relationship(foreign_keys=[reporter_id])
    reported: Mapped["User"] = relationship(foreign_keys=[reported_user_id])
