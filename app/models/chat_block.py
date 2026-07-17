from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ChatBlock(Base, TimestampMixin):
    """Одностороннее «блокирование для себя»: blocker перестаёт видеть чаты
    и получать уведомления от blocked. Собеседника это никак не ограничивает."""

    __tablename__ = "chat_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_chat_block_pair"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    blocked_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
