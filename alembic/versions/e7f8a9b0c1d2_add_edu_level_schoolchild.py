"""add 'schoolchild' value to edu_level enum

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-07-17 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Школьник — «ниже» бакалавриата.
    # ADD VALUE нельзя выполнять внутри транзакционного блока, а Alembic
    # оборачивает миграцию в транзакцию → завершаем её перед ALTER TYPE.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE edu_level ADD VALUE IF NOT EXISTS 'schoolchild' "
        "BEFORE 'bachelor'"
    )


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения из enum.
    # Откат невозможен без пересоздания типа; оставляем no-op.
    pass
