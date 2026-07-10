"""SQLAlchemy ORM models for differential analysis.

A DifferentialRun tests a cohort clustering run for changes across experimental
groups. It produces two result tables:

  * DAResult - differential ABUNDANCE: does a population's frequency differ
    between groups (edgeR / rank test on per-sample counts).
  * DSResult - differential STATE: within a population, does a marker's
    expression differ between groups (limma / rank test on per-sample medians).

Results are relational (not JSON blobs) so the API can sort/filter server-side.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DifferentialRun(Base):
    __tablename__ = "differential_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clustering_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("clustering_runs.id"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(String, nullable=False)
    # "diffcyt" (edgeR/limma via R) or "python" (scipy rank-test fallback).
    engine: Mapped[str] = mapped_column(String, nullable=False, default="python")
    params: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # {reason: [markers/samples excluded]} for transparency.
    notes: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    da_results: Mapped[list["DAResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    ds_results: Mapped[list["DSResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class DAResult(Base):
    """Differential abundance: one row per population."""

    __tablename__ = "da_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    differential_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("differential_runs.id"), nullable=False, index=True
    )
    metacluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    log_fc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_adj: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    log_cpm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    run: Mapped["DifferentialRun"] = relationship(back_populates="da_results")


class DSResult(Base):
    """Differential state: one row per (population, marker)."""

    __tablename__ = "ds_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    differential_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("differential_runs.id"), nullable=False, index=True
    )
    metacluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    marker: Mapped[str] = mapped_column(String, nullable=False)
    log_fc: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_adj: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    run: Mapped["DifferentialRun"] = relationship(back_populates="ds_results")
