"""request cancel flags: cancel_requested, cancel_disputed

Revision ID: d4e5f6a7b8ca
Revises: c3d4e5f6a7b9
Create Date: 2026-07-18 02:10:00.000000

Изменения (задача 8, асимметричная модель завершения/отмены):
- requests: + cancel_requested (NOT NULL Boolean, server_default 'false') —
  отправитель запросил отмену, ждём согласия объясняющего.
- requests: + cancel_disputed (NOT NULL Boolean, server_default 'false') —
  объясняющий отклонил отмену, спор ушёл админу на разбор.
server_default покрывает существующие строки.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8ca'
down_revision: Union[str, None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'requests',
        sa.Column(
            'cancel_requested',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )
    op.add_column(
        'requests',
        sa.Column(
            'cancel_disputed',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )


def downgrade() -> None:
    op.drop_column('requests', 'cancel_disputed')
    op.drop_column('requests', 'cancel_requested')
