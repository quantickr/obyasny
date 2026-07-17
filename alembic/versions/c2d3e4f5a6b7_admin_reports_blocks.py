"""admin flag, ban, reports, personal chat blocks

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-17 18:00:00.000000

Изменения:
- users: + is_admin, is_banned.
- reports: жалобы (reporter → reported), контекст (board/profile/chat), статус.
- chat_blocks: одностороннее «блокирование для себя».
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) users: флаги админа и бана.
    op.add_column(
        "users",
        sa.Column(
            "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_banned", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.alter_column("users", "is_admin", server_default=None)
    op.alter_column("users", "is_banned", server_default=None)

    # 2) reports.
    report_status = sa.Enum(
        "open", "resolved", "dismissed", name="report_status"
    )
    report_context = sa.Enum(
        "board", "profile", "chat", name="report_context"
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("reporter_id", sa.BigInteger(), nullable=False),
        sa.Column("reported_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "context", report_context, nullable=False, server_default="board"
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status", report_status, nullable=False, server_default="open"
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["reporter_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reported_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["chats.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_status", "reports", ["status"])

    # 3) chat_blocks.
    op.create_table(
        "chat_blocks",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("blocker_id", sa.BigInteger(), nullable=False),
        sa.Column("blocked_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["blocker_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["blocked_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "blocker_id", "blocked_id", name="uq_chat_block_pair"
        ),
    )
    op.create_index(
        "ix_chat_blocks_blocker_id", "chat_blocks", ["blocker_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_blocks_blocker_id", table_name="chat_blocks")
    op.drop_table("chat_blocks")

    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_table("reports")
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="report_context").drop(op.get_bind(), checkfirst=True)

    op.drop_column("users", "is_banned")
    op.drop_column("users", "is_admin")
