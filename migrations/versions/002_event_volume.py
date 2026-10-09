"""Generic event-volume observations.

Revision ID: 002_event_volume
Revises: 001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "002_event_volume"
down_revision = "001_initial"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "event_volume_observations",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_count", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("event_count >= 0", name="ck_event_volume_nonnegative"),
        sa.CheckConstraint("window_end > window_start", name="ck_event_volume_valid_window"),
        sa.UniqueConstraint("source_id", "window_start", "window_end", name="uq_event_volume_source_window"),
    )
    op.create_index("ix_event_volume_window_end", "event_volume_observations", ["window_end"])

def downgrade():
    op.drop_index("ix_event_volume_window_end", table_name="event_volume_observations")
    op.drop_table("event_volume_observations")
