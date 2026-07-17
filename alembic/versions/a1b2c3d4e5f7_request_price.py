"""request price: requests.price

Revision ID: a1b2c3d4e5f7
Revises: f5a6b7c8d9e0
Create Date: 2026-07-18 00:00:00.000000

Изменения:
- requests: + price (NOT NULL SmallInteger, server_default '1'). Цена в
  шоколадках, зафиксированная при создании заявки (из темы объясняющего).
  0 → бесплатное объяснение. server_default '1' покрывает существующие строки
  (старые заявки продолжают работать как «1 шоколадка»).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "requests",
        sa.Column(
            "price",
            sa.SmallInteger(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("requests", "price")
