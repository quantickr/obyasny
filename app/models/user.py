from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.topic import UserTopic


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR telegram_id IS NOT NULL",
            name="ck_user_has_login_method",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Вход по email/паролю (опционально)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Связка с Telegram
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, nullable=True, index=True
    )
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    show_tg_username: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Денормализованный баланс (источник истины — chocolate_transactions)
    chocolate_balance: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    user_topics: Mapped[list["UserTopic"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
