"""user rating: users.rating

Revision ID: c3d4e5f6a7b9
Revises: b2c3d4e5f6a8
Create Date: 2026-07-18 01:10:00.000000

Изменения:
- users: + rating (NOT NULL Integer, server_default '0'). Рейтинг репутации:
  +1 за завершённое объяснение (+2 если бесплатно), −5 виноватому и +1 репортёру
  за доказанную жалобу. Все стартуют с 0; может быть отрицательным.
  server_default '0' покрывает существующие строки.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b9'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "rating",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "rating")
