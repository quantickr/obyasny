"""add user.on_board

Revision ID: a1b2c3d4e5f6
Revises: e6ab160bb7b5
Create Date: 2026-07-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e6ab160bb7b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default=false, чтобы существующие строки получили значение
    # без ошибки NOT NULL.
    op.add_column(
        'users',
        sa.Column(
            'on_board',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'on_board')
