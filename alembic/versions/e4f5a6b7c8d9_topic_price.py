"""topic price: user_topics.price

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-17 21:00:00.000000

Изменения:
- user_topics: + price (nullable SmallInteger). Цена в шоколадках за объяснение
  темы (только для kind == can_teach). None → трактуется как 1; диапазон 1..3.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, None] = 'd3e4f5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_topics",
        sa.Column("price", sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_topics", "price")
