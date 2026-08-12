"""pose velocity for inertial runs

Revision ID: 61499c968ccc
Revises: 723726176e7a
Create Date: 2026-08-11 02:56:24.162057

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '61499c968ccc'
down_revision: Union[str, Sequence[str], None] = '723726176e7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable because a visual-only run has no scale and therefore no speed to record
    op.add_column('poses', sa.Column('vx', sa.Float(), nullable=True))
    op.add_column('poses', sa.Column('vy', sa.Float(), nullable=True))
    op.add_column('poses', sa.Column('vz', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('poses', 'vz')
    op.drop_column('poses', 'vy')
    op.drop_column('poses', 'vx')
