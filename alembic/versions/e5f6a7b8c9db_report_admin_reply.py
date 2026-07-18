"""report admin reply: reports.admin_reply, reports.resolved_by

Revision ID: e5f6a7b8c9db
Revises: d4e5f6a7b8ca
Create Date: 2026-07-18 02:15:00.000000

Изменения (задача 9, ответы админа на жалобы):
- reports: + admin_reply (Text, nullable) — текстовый ответ админа репортёру,
  виден на странице «Мои жалобы».
- reports: + resolved_by (BigInteger, FK users.id ON DELETE SET NULL) — какой
  админ закрыл жалобу.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9db'
down_revision: Union[str, None] = 'd4e5f6a7b8ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'reports',
        sa.Column('admin_reply', sa.Text(), nullable=True),
    )
    op.add_column(
        'reports',
        sa.Column('resolved_by', sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        'fk_reports_resolved_by',
        'reports',
        'users',
        ['resolved_by'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_reports_resolved_by', 'reports', type_='foreignkey')
    op.drop_column('reports', 'resolved_by')
    op.drop_column('reports', 'admin_reply')
