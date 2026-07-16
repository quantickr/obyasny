"""add message.reply_to_id, request.blocked_until and pair index

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ответ на сообщение (reply): ссылка на исходное сообщение того же чата.
    op.add_column(
        'messages',
        sa.Column('reply_to_id', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_messages_reply_to_id',
        'messages',
        'messages',
        ['reply_to_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # Блокировка повторных заявок от отправителя после отказа.
    op.add_column(
        'requests',
        sa.Column('blocked_until', sa.DateTime(timezone=True), nullable=True),
    )

    # Быстрая проверка дубля заявки по паре (sender, receiver, status).
    op.create_index(
        'ix_requests_pair_status',
        'requests',
        ['sender_id', 'receiver_id', 'status'],
    )


def downgrade() -> None:
    op.drop_index('ix_requests_pair_status', table_name='requests')
    op.drop_column('requests', 'blocked_until')
    op.drop_constraint('fk_messages_reply_to_id', 'messages', type_='foreignkey')
    op.drop_column('messages', 'reply_to_id')
