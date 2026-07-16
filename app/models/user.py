from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.topic import UserTopic


class EduLevel(str, enum.Enum):
    bachelor = "bachelor"
    specialist = "specialist"
    master = "master"
    postgrad = "postgrad"


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NOT NULL OR telegram_id IS NOT NULL",
            name="ck_user_has_login_method",
        ),
        CheckConstraint(
            "course BETWEEN 1 AND 6",
            name="ck_user_course_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Вход по email/паролю (опционально)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Учебные данные (обязательные при регистрации)
    university: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    edu_level: Mapped[EduLevel] = mapped_column(
        Enum(EduLevel, name="edu_level"), nullable=False
    )

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

    # Пользователь добровольно выложен на доску (/board)
    on_board: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    user_topics: Mapped[list["UserTopic"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
