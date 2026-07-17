"""admin roles: is_superadmin + can_manage_reports/can_punish/can_edit_profiles

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-17 22:00:00.000000

Изменения:
- users: + is_superadmin, can_manage_reports, can_punish, can_edit_profiles
  (boolean NOT NULL, default false). Гранулярные права мини-админов; суперадмин
  назначает их и обходит все проверки.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f5a6b7c8d9e0'
down_revision: Union[str, None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = (
    "is_superadmin",
    "can_manage_reports",
    "can_punish",
    "can_edit_profiles",
)


def upgrade() -> None:
    for name in _COLUMNS:
        op.add_column(
            "users",
            sa.Column(
                name,
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        # Значение по умолчанию нужно только для заполнения существующих строк.
        op.alter_column("users", name, server_default=None)


def downgrade() -> None:
    for name in reversed(_COLUMNS):
        op.drop_column("users", name)
