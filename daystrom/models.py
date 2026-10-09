"""Persistent inventory and activity observations."""
from datetime import datetime
from typing import Any
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Identity, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = 'sources'
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_name: Mapped[str] = mapped_column(String(512), nullable=False)
    labels: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    observations: Mapped[list['ActivityObservation']] = relationship(back_populates='source')
    __table_args__ = (
        UniqueConstraint('source_type', 'source_key', name='uq_sources_type_key'),
        Index('ix_sources_last_discovered_at', 'last_discovered_at'),
    )


class ActivityObservation(Base):
    __tablename__ = 'activity_observations'
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey('sources.id', ondelete='CASCADE'), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    event_age_seconds: Mapped[int | None] = mapped_column(Integer)
    observation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[Source] = relationship(back_populates='observations')
    __table_args__ = (Index('ix_activity_source_observed', 'source_id', 'observed_at'),)


class EventVolumeObservation(Base):
    """Count of events for a source in a bounded UTC time window."""
    __tablename__ = "event_volume_observations"
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    source: Mapped["Source"] = relationship()
    __table_args__ = (
        UniqueConstraint("source_id", "window_start", "window_end", name="uq_event_volume_source_window"),
        Index("ix_event_volume_window_end", "window_end"),
    )
