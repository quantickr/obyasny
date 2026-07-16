"""add 'specialist' value to edu_level enum

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Специалитет — между бакалавриатом и магистратурой.
    # ADD VALUE нельзя выполнять внутри транзакционного блока, а Alembic
    # оборачивает миграцию в транзакцию → завершаем её перед ALTER TYPE.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE edu_level ADD VALUE IF NOT EXISTS 'specialist' "
        "BEFORE 'master'"
    )


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значения из enum.
    # Откат невозможен без пересоздания типа; оставляем no-op.
    pass
