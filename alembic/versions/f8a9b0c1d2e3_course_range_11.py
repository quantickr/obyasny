"""widen course range constraint to 1..11 (schoolchild classes)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-07-17 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f8a9b0c1d2e3'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Школьники: класс 1..11 (тот же столбец course).
    op.drop_constraint('ck_user_course_range', 'users', type_='check')
    op.create_check_constraint(
        'ck_user_course_range', 'users', 'course BETWEEN 1 AND 11'
    )


def downgrade() -> None:
    op.drop_constraint('ck_user_course_range', 'users', type_='check')
    op.create_check_constraint(
        'ck_user_course_range', 'users', 'course BETWEEN 1 AND 6'
    )
