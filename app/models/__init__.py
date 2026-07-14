"""Импорт всех моделей — нужен для Alembic autogenerate и корректной
регистрации связей в общем MetaData."""

from app.models.base import Base
from app.models.chat import Chat, Message
from app.models.chocolate import ChocolateTransaction
from app.models.listing import Listing, ListingResponse
from app.models.match import Match
from app.models.request import Request
from app.models.topic import Topic, UserTopic
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Topic",
    "UserTopic",
    "Listing",
    "ListingResponse",
    "Request",
    "Match",
    "Chat",
    "Message",
    "ChocolateTransaction",
]
