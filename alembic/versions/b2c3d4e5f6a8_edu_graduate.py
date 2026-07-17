"""add 'graduate' value to edu_level enum

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-18 01:00:00.000000

Изменения:
- edu_level: + 'graduate' (выпустившийся). Добавляется в конец типа. У выпустившихся
  курс не показывается (сервис фиксирует course=1).
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b2c3d4e5f6a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # «Выпустившийся» — в конец типа (после аспирантуры).
    # ADD VALUE нельзя выполнять внутри транзакционного блока, а Alembic
    # оборачивает миграцию в транзакцию → завершаем её перед ALTER TYPE.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE edu_level ADD VALUE IF NOT EXISTS 'graduate' "
        "AFTER 'postgrad'"
    )


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения из enum.
    # Откат невозможен без пересоздания типа; оставляем no-op.
    pass
