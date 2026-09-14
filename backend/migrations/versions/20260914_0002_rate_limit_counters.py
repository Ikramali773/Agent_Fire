"""Shared rate-limit counters.

The rate limiter kept its counters in one worker's memory, so they reset on
restart and were not shared - behind N workers the effective limit was N
times the configured one, which an attacker multiplies simply by opening
more connections. This table moves them into the database every worker
already talks to.

Holds at most the last minute of attempts: every check deletes everything
older than the window. A counter, not a log.

Revision ID: 0002_rate_limit
Revises: 0001_baseline
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_rate_limit"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('rate_limit_attempts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rate_limit_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rate_limit_attempts_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_rate_limit_attempts_key'), ['key'], unique=False)



def downgrade() -> None:
    """Drops the counters. Safe: they are rebuilt by use, and losing a
    minute of them costs nothing."""
    with op.batch_alter_table('rate_limit_attempts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rate_limit_attempts_key'))
        batch_op.drop_index(batch_op.f('ix_rate_limit_attempts_created_at'))

    op.drop_table('rate_limit_attempts')
