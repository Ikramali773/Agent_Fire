"""Organisations, team projects, and review assignment.

Sharing was one project to one person at a time: six colleagues and forty
projects meant two hundred and forty shares, and someone leaving meant
remembering all of them. An organisation is a named group of accounts; a
project shared with it is readable by every member, and a member who
leaves loses that access in one step.

`organisation_case_files` is a link table rather than a column on
case_files, deliberately - which group can see a project is a relationship
between two things, not a fact about the building, and the Case File model
stays untouched.

`case_file_assignments` is append-only, like case_file_reviews: a case
reassigned twice reads differently from one assigned once, and an UPDATE
in place could not tell you which you were looking at. A row with no
assignee means explicitly unassigned.

Revision ID: 0004_organisations
Revises: 0003_preferences
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_organisations"
down_revision: Union[str, Sequence[str], None] = "0003_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('case_file_assignments',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('assigned_to_user_id', sa.String(), nullable=True),
    sa.Column('assigned_to_email', sa.String(), nullable=True),
    sa.Column('assigned_by_user_id', sa.String(), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('case_file_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_case_file_assignments_assigned_to_user_id'), ['assigned_to_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_case_file_assignments_session_id'), ['session_id'], unique=False)

    op.create_table('organisation_case_files',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('organisation_id', sa.String(), nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('added_by_user_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organisation_id', 'session_id', name='uq_org_case_file')
    )
    with op.batch_alter_table('organisation_case_files', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organisation_case_files_organisation_id'), ['organisation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_organisation_case_files_session_id'), ['session_id'], unique=False)

    op.create_table('organisation_members',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('organisation_id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('added_by_user_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organisation_id', 'user_id', name='uq_org_member')
    )
    with op.batch_alter_table('organisation_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organisation_members_organisation_id'), ['organisation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_organisation_members_user_id'), ['user_id'], unique=False)

    op.create_table('organisations',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('created_by_user_id', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('organisations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_organisations_created_by_user_id'), ['created_by_user_id'], unique=False)



def downgrade() -> None:
    """Drops the four tables. Every project survives - an organisation is
    a way of sharing them, never where they live - but who could see what,
    and who owed which review, is gone."""
    with op.batch_alter_table('organisations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organisations_created_by_user_id'))

    op.drop_table('organisations')
    with op.batch_alter_table('organisation_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organisation_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_organisation_members_organisation_id'))

    op.drop_table('organisation_members')
    with op.batch_alter_table('organisation_case_files', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_organisation_case_files_session_id'))
        batch_op.drop_index(batch_op.f('ix_organisation_case_files_organisation_id'))

    op.drop_table('organisation_case_files')
    with op.batch_alter_table('case_file_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_case_file_assignments_session_id'))
        batch_op.drop_index(batch_op.f('ix_case_file_assignments_assigned_to_user_id'))

    op.drop_table('case_file_assignments')
