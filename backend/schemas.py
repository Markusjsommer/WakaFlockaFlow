"""Pydantic v2 request/response models matching the REST contract.

Shapes mirror the FastAPI routes under /api/v1 exactly so the frontend and
backend slices link up without translation.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Mandatory integrity guardrail — surfaced on every screen and in exports.
BANNER = "SYNTHETIC BATCH EFFECT — mechanism demo, not real multi-batch data"


# ---- sessions ----------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    name: Optional[str] = None


class SessionCreateResponse(BaseModel):
    session_id: str


# ---- files -------------------------------------------------------------------

class FileMeta(BaseModel):
    """One row of POST/GET /sessions/{sid}/files."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    n_events: int
    n_channels: int


# ---- transform ---------------------------------------------------------------

class TransformParams(BaseModel):
    cofactor: float = 150.0


class TransformRequest(BaseModel):
    method: str = "arcsinh"
    params: TransformParams = Field(default_factory=TransformParams)


class OkResponse(BaseModel):
    ok: bool = True


# ---- batch correction --------------------------------------------------------

class BatchCorrectionRequest(BaseModel):
    n_batches: int = 2
    drift_markers: list[str] = Field(default_factory=list)
    drift_a: float = 1.3
    drift_b: float = 0.2
    nClus: int = 10
    nQ: int = 101
    seed: int = 42
    engine: Literal["cytonorm", "pycombat"] = "cytonorm"


class JobRef(BaseModel):
    """Returned immediately by long-running POST endpoints."""

    job_id: str


class InjectedMarker(BaseModel):
    a: float
    b: float
    batch: str


class PerMarkerEmd(BaseModel):
    before: float
    after: float


class BatchCorrectionRunResponse(BaseModel):
    id: str
    status: str
    synthetic: bool = True
    banner: str = BANNER
    mean_emd_before: float
    mean_emd_after: float
    reduction_pct: float
    per_marker: dict[str, PerMarkerEmd]
    umap_before: list[list[Any]]
    umap_after: list[list[Any]]
    injected: dict[str, InjectedMarker]


# ---- jobs --------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    """GET /jobs/{job_id} — polled every 2s while pending/running."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    status: str
    progress: int
    message: Optional[str] = None
    error: Optional[str] = None
    result: Optional[Any] = None
