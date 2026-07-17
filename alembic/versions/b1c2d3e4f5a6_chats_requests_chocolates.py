"""per-request chats, mutual completion, chocolate economy

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-07-17 15:00:00.000000

Изменения:
- chats: снятие UNIQUE(user1_id, user2_id) — теперь на каждую заявку свой чат;
  + title, completed_at, hidden_user1, hidden_user2.
- requests: + sender_done, receiver_done, completed_at; enum request_status += 'completed'.
- users: + last_weekly_at.
- chocolate_reason enum += 'spend', 'refund', 'weekly'.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'a9b0c1d2e3f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Новые значения enum. ADD VALUE нельзя внутри транзакции —
    # завершаем текущую перед ALTER TYPE.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'completed'"
    )
    op.execute(
        "ALTER TYPE chocolate_reason ADD VALUE IF NOT EXISTS 'spend'"
    )
    op.execute(
        "ALTER TYPE chocolate_reason ADD VALUE IF NOT EXISTS 'refund'"
    )
    op.execute(
        "ALTER TYPE chocolate_reason ADD VALUE IF NOT EXISTS 'weekly'"
    )

    # 2) chats: снимаем UNIQUE на пару юзеров (новый чат на каждую заявку).
    op.drop_constraint("uq_chat_users", "chats", type_="unique")
    op.add_column(
        "chats", sa.Column("title", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "chats", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "chats",
        sa.Column(
            "hidden_user1", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "chats",
        sa.Column(
            "hidden_user2", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.alter_column("chats", "hidden_user1", server_default=None)
    op.alter_column("chats", "hidden_user2", server_default=None)

    # 3) requests: флаги обоюдного завершения.
    op.add_column(
        "requests",
        sa.Column(
            "sender_done", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "requests",
        sa.Column(
            "receiver_done", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "requests",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("requests", "sender_done", server_default=None)
    op.alter_column("requests", "receiver_done", server_default=None)

    # 4) users: время последней еженедельной выдачи.
    op.add_column(
        "users",
        sa.Column("last_weekly_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "last_weekly_at")

    op.drop_column("requests", "completed_at")
    op.drop_column("requests", "receiver_done")
    op.drop_column("requests", "sender_done")

    op.drop_column("chats", "hidden_user2")
    op.drop_column("chats", "hidden_user1")
    op.drop_column("chats", "completed_at")
    op.drop_column("chats", "title")
    op.create_unique_constraint(
        "uq_chat_users", "chats", ["user1_id", "user2_id"]
    )

    # PostgreSQL не поддерживает удаление значений enum — оставляем как есть.
