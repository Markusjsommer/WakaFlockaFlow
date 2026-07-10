"""SQLAlchemy ORM models for automated population identification.

Two tables layered on top of the shared Base (from db.py):
  * ClusteringRun - one FlowSOM+UMAP run against an FCS file in a session.
  * Population    - one identified cell population (metacluster) within a run.

Field names mirror the SLICE A contract so the API and frontend link exactly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base

# Colorblind-safe qualitative palette for default population colors.
# Paul Tol's "bright" scheme followed by the Okabe-Ito set and Tol "muted"
# extras; every entry is distinguishable under deuteranopia/protanopia and the
# first eight are ordered for maximum separation (most populations use those).
POPULATION_PALETTE = [
    "#4477AA",  # blue
    "#EE6677",  # rose
    "#228833",  # green
    "#CCBB44",  # olive-yellow
    "#66CCEE",  # cyan
    "#AA3377",  # purple
    "#E69F00",  # orange
    "#0072B2",  # deep blue
    "#009E73",  # bluish green
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
    "#332288",  # indigo
    "#117733",  # dark green
    "#882255",  # wine
    "#999933",  # olive
    "#56B4E9",  # sky
]


def palette_color(index: int) -> str:
    """Default population color for the ``index``-th population (wraps the palette)."""
    return POPULATION_PALETTE[int(index) % len(POPULATION_PALETTE)]


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClusteringRun(Base):
    __tablename__ = "clustering_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String, ForeignKey("sessions.id"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(String, nullable=False)
    # Legacy/fallback single-file pointer. Cohort runs use the run_samples join.
    fcs_file_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    params: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    n_populations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    umap: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Cohort support. "single" = one FCS file (legacy behaviour); "cohort" = a
    # pooled run over run_samples. server_default keeps legacy rows readable as
    # "single" after the ALTER TABLE shim (see models_cluster.ensure_columns).
    mode: Mapped[str] = mapped_column(
        String, nullable=False, default="single", server_default="single"
    )
    # Canonical marker names actually clustered on (intersection across samples).
    shared_markers: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # {sample_label: [markers absent from that sample and therefore dropped]}.
    dropped_markers: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # Absolute path to data/runs/{run_id}/labels.npz (per-cell labels artifact).
    labels_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    n_samples: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    populations: Mapped[list["Population"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    samples: Mapped[list["ClusteringRunSample"]] = relationship(
        back_populates="run", cascade="all, delete-orphan",
        order_by="ClusteringRunSample.sample_index",
    )


class Population(Base):
    __tablename__ = "populations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clustering_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("clustering_runs.id"), nullable=False
    )
    parent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    metacluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage_of_parent: Mapped[float] = mapped_column(Float, nullable=False)
    median_expression: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    color: Mapped[str] = mapped_column(String, nullable=False, default="#4DBBD5")
    is_manual_gate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    run: Mapped["ClusteringRun"] = relationship(back_populates="populations")


class ClusteringRunSample(Base):
    """One FCS file participating in a cohort run, with experimental tags.

    A single-file run has no rows here (it uses ClusteringRun.fcs_file_id). A
    cohort run has one row per selected file; ``sample_index`` is the compact
    integer code stored per cell in the labels artifact and the UMAP 4-tuples.
    """

    __tablename__ = "clustering_run_samples"
    __table_args__ = (
        UniqueConstraint("clustering_run_id", "sample_index"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clustering_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("clustering_runs.id"), nullable=False, index=True
    )
    fcs_file_id: Mapped[str] = mapped_column(String, nullable=False)
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_label: Mapped[str] = mapped_column(String, nullable=False)
    group: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    batch: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    covariates: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    # True full-file event count (the honest denominator for percentages).
    n_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Events this sample actually contributed to the pool after capping.
    n_events_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    run: Mapped["ClusteringRun"] = relationship(back_populates="samples")


class PopulationSampleStat(Base):
    """population x sample quantification: the source for differential testing.

    Small: n_metaclusters * n_samples rows. Population keeps the *pooled*
    aggregates; per-sample numbers live only here.
    """

    __tablename__ = "population_sample_stats"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    clustering_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("clustering_runs.id"), nullable=False, index=True
    )
    population_id: Mapped[str] = mapped_column(
        String, ForeignKey("populations.id"), nullable=False, index=True
    )
    run_sample_id: Mapped[str] = mapped_column(
        String, ForeignKey("clustering_run_samples.id"), nullable=False, index=True
    )
    # Denormalized for fast pivots without extra joins.
    metacluster_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    percentage_of_sample: Mapped[float] = mapped_column(Float, nullable=False)
    median_expression: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)


def ensure_columns(engine) -> None:
    """Idempotently add cohort columns to the pre-existing clustering_runs table.

    SQLAlchemy's ``create_all`` creates missing *tables* but never adds *columns*
    to a table that already exists. This backfills legacy databases so old runs
    read as ``mode='single'`` without a full migration framework.
    """
    additions = [
        ("mode", "TEXT NOT NULL DEFAULT 'single'"),
        ("shared_markers", "JSON"),
        ("dropped_markers", "JSON"),
        ("labels_path", "TEXT"),
        ("n_samples", "INTEGER"),
    ]
    with engine.begin() as cx:
        existing = {
            row[1]
            for row in cx.exec_driver_sql("PRAGMA table_info(clustering_runs)")
        }
        for name, ddl in additions:
            if name not in existing:
                cx.exec_driver_sql(
                    f"ALTER TABLE clustering_runs ADD COLUMN {name} {ddl}"
                )
