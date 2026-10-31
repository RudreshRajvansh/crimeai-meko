"""access request fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-10 15:37:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('designation', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('account_status', sa.String(length=20), server_default='approved', nullable=False))
    op.add_column('users', sa.Column('request_id', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('approved_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('users', sa.Column('rejection_reason', sa.String(length=500), nullable=True))
    
    op.create_index(op.f('ix_users_account_status'), 'users', ['account_status'], unique=False)
    op.create_index(op.f('ix_users_request_id'), 'users', ['request_id'], unique=True)
    op.create_foreign_key('fk_users_approved_by_users', 'users', 'users', ['approved_by'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_users_approved_by_users', 'users', type_='foreignkey')
    op.drop_index(op.f('ix_users_request_id'), table_name='users')
    op.drop_index(op.f('ix_users_account_status'), table_name='users')
    op.drop_column('users', 'rejection_reason')
    op.drop_column('users', 'approved_by')
    op.drop_column('users', 'approved_at')
    op.drop_column('users', 'request_id')
    op.drop_column('users', 'account_status')
    op.drop_column('users', 'designation')
