"""SQLAlchemy ORM models for the synthetic batch-correction demo.

Four tables: Session, FCSFile, Job, BatchCorrectionRun.
Field names mirror the PRD so later phases stay additive.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    files: Mapped[list["FCSFile"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    runs: Mapped[list["BatchCorrectionRun"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class FCSFile(Base):
    __tablename__ = "fcs_files"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    n_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_channels: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["Session"] = relationship(back_populates="files")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    result: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class BatchCorrectionRun(Base):
    __tablename__ = "batch_correction_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.id"), nullable=False
    )
    params: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    engine: Mapped[str] = mapped_column(String, nullable=False)
    emd_before: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    emd_after: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    mean_emd_before: Mapped[Optional[float]] = mapped_column(nullable=True)
    mean_emd_after: Mapped[Optional[float]] = mapped_column(nullable=True)
    reduction_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    umap_before: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    umap_after: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    injected: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    corrected_dir: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["Session"] = relationship(back_populates="runs")
