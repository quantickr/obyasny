from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ListingStatus(str, enum.Enum):
    open = "open"
    closed = "closed"
    archived = "archived"


class ResponseStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"


class Listing(Base, TimestampMixin):
    """Доска объявлений: 'умею объяснить X, хочу узнать Y'."""

    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_listings_teach_status", "teach_topic_id", "status"),
        Index("ix_listings_learn_status", "learn_topic_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    teach_topic_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    learn_topic_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ListingStatus] = mapped_column(
        Enum(ListingStatus, name="listing_status"),
        default=ListingStatus.open,
        nullable=False,
    )


class ListingResponse(Base, TimestampMixin):
    __tablename__ = "listing_responses"
    __table_args__ = (
        UniqueConstraint(
            "listing_id", "responder_id", name="uq_listing_responder"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("listings.id", ondelete="CASCADE"), nullable=False
    )
    responder_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ResponseStatus] = mapped_column(
        Enum(ResponseStatus, name="response_status"),
        default=ResponseStatus.pending,
        nullable=False,
    )
