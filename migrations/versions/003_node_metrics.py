"""Curated five-minute node metrics.

Revision ID: 003_node_metrics
Revises: 002_event_volume
"""
from alembic import op
import sqlalchemy as sa
revision = '003_node_metrics'
down_revision = '002_event_volume'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('node_metric_observations',
        sa.Column('id', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('instance', sa.String(256), nullable=False),
        sa.Column('metric_name', sa.String(64), nullable=False),
        sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('instance', 'metric_name', 'window_end', name='uq_node_metric_instance_name_end'),
    )
    op.create_index('ix_node_metric_window_end', 'node_metric_observations', ['window_end'])

def downgrade():
    op.drop_index('ix_node_metric_window_end', table_name='node_metric_observations')
    op.drop_table('node_metric_observations')
