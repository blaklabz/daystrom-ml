"""Initial Daystrom source inventory and activity observations.

Revision ID: 001_initial
Revises:
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sources',
        sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('source_type', sa.String(length=16), nullable=False),
        sa.Column('source_key', sa.String(length=64), nullable=False),
        sa.Column('source_name', sa.String(length=512), nullable=False),
        sa.Column('labels', postgresql.JSONB(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_discovered_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('source_type', 'source_key', name='uq_sources_type_key'),
    )
    op.create_index('ix_sources_last_discovered_at', 'sources', ['last_discovered_at'])
    op.create_table(
        'activity_observations',
        sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('source_id', sa.BigInteger(), sa.ForeignKey('sources.id', ondelete='CASCADE'), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_event_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('event_age_seconds', sa.Integer(), nullable=True),
        sa.Column('observation_status', sa.String(length=32), nullable=False),
    )
    op.create_index('ix_activity_source_observed', 'activity_observations', ['source_id', 'observed_at'])


def downgrade() -> None:
    op.drop_index('ix_activity_source_observed', table_name='activity_observations')
    op.drop_table('activity_observations')
    op.drop_index('ix_sources_last_discovered_at', table_name='sources')
    op.drop_table('sources')
