"""Per-user preferences.

A pinned chat is per-USER state, and the Case File schema is fixed - there
is no field on it for "this person pinned this project", and inventing one
would put one account's preference on a record that gets shared with
reviewers. So pins lived in localStorage and did not follow the account to
a second browser or a phone. This is where they live now.

One row per account holding one JSON blob, for the reason case_files is a
blob: preferences are read and written whole, and nothing queries an
individual preference in SQL.

Revision ID: 0003_preferences
Revises: 0002_rate_limit
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_preferences"
down_revision: Union[str, Sequence[str], None] = "0002_rate_limit"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_preferences',
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('data', sa.JSON(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('user_id')
    )


def downgrade() -> None:
    """Drops the table. Loses every pin, which is a preference and not a
    fact about a building - recoverable by pinning again."""
    op.drop_table('user_preferences')
