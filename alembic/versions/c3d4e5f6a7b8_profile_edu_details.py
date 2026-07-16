"""add user.university/course/edu_level and user_topic.details

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


edu_level_enum = sa.Enum(
    'bachelor', 'master', 'postgrad', name='edu_level'
)


def upgrade() -> None:
    edu_level_enum.create(op.get_bind(), checkfirst=True)

    # Учебные данные пользователя. БД чистая → NOT NULL без server_default.
    op.add_column(
        'users',
        sa.Column('university', sa.String(length=200), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('course', sa.SmallInteger(), nullable=False),
    )
    op.add_column(
        'users',
        sa.Column('edu_level', edu_level_enum, nullable=False),
    )
    op.create_check_constraint(
        'ck_user_course_range', 'users', 'course BETWEEN 1 AND 6'
    )

    # Что именно непонятно (для тем «хочу узнать»).
    op.add_column(
        'user_topics',
        sa.Column('details', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_topics', 'details')
    op.drop_constraint('ck_user_course_range', 'users', type_='check')
    op.drop_column('users', 'edu_level')
    op.drop_column('users', 'course')
    op.drop_column('users', 'university')
    edu_level_enum.drop(op.get_bind(), checkfirst=True)
