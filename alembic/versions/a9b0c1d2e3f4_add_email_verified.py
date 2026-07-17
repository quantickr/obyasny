"""add user.email_verified

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-07-17 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9b0c1d2e3f4'
down_revision: Union[str, None] = 'f8a9b0c1d2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default=false, чтобы существующие строки получили значение
    # без ошибки NOT NULL.
    op.add_column(
        'users',
        sa.Column(
            'email_verified',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Backfill: не блокируем уже существующих пользователей с почтой —
    # считаем их email подтверждённым. Подтверждение требуется только для
    # новых регистраций и смен email после этой миграции.
    op.execute("UPDATE users SET email_verified = TRUE WHERE email IS NOT NULL")
    # Снимаем server_default — дальше значение задаёт приложение (default=False).
    op.alter_column('users', 'email_verified', server_default=None)


def downgrade() -> None:
    op.drop_column('users', 'email_verified')
