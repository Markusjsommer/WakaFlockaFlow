"""REST API for automated cell population identification.

Endpoints under /api/v1 that drive the population-ID workflow:
  * panel/template   - marker panel for the config UI (which channels to cluster on)
  * clustering (POST)- kick off a FlowSOM + UMAP run on a worker thread; returns {job_id}
  * clustering (GET) - list / fetch runs and their identified populations
  * populations PATCH- rename / recolor a population
  * export           - reproducibility bundle (.zip: CSVs + provenance)

Long-running work is submitted to ``jobs.executor`` (the shared ThreadPoolExecutor) and
each DB write inside a worker uses a FRESH ``SessionLocal()`` - worker threads must never
share the request-scoped session. The frontend polls GET /api/v1/jobs/{id} for progress.
"""
from __future__ import annotations

import csv
import io as _io
import json
import uuid
import zipfile
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as SASession

from db import SessionLocal, get_db
from models import Session as SessionModel, FCSFile, Job
from models_cluster import (
    ClusteringRun,
    ClusteringRunSample,
    Population,
    PopulationSampleStat,
    palette_color,
)
from analysis import io as analysis_io
from analysis import cluster
from analysis import annotate as _annotate
from analysis import cohort as _cohort
from analysis import state_axes as _state_axes

# Per-session channel -> marker-name overrides (the panel editor). Lets fluorophore-
# named files (e.g. BUV395-A -> CD19) be annotated. Empty = use the file's own names.
PANEL_MARKERS: dict[str, dict] = {}

# The bundled real acquisition used as the fallback data source.
import os as _os
from pathlib import Path as _Path

_REPO_ROOT = _Path(__file__).resolve().parent.parent
DEMO_FILE = str(_REPO_ROOT / "sample_data" / "spectral_pbmc" / "PBMC_spectral_UNMIXED.fcs")
E1_PATH = str(_REPO_ROOT / "PBMC_40color_E1_UNMIXED.fcs")


def _fallback_path() -> str:
    """No session file? Prefer the bundled permissive demo; then the local E1 fixture."""
    if _os.path.exists(DEMO_FILE):
        return DEMO_FILE
    return E1_PATH

# Cache of loaded event matrices keyed by path: path -> (events, channel_names, marker_labels).
# Bounded: a cohort can reference hundreds of files, so keep only the most recent
# few to avoid unbounded memory growth.
_EVENTS_CACHE: dict[str, tuple] = {}
_EVENTS_CACHE_MAX = 8

# Per-cell labels are persisted here (not in the DB) so FlowJo/gate-path export
# never has to re-run FlowSOM: data/runs/{run_id}/labels.npz.
_RUNS_DIR = _REPO_ROOT / "data" / "runs"

router = APIRouter(prefix="/api/v1")


def _labels_path(run_id: str) -> str:
    return str(_RUNS_DIR / run_id / "labels.npz")


def _save_labels(run_id: str, labels, sample_idx=None) -> str:
    """Persist per-cell metacluster labels (and cohort sample codes) to disk."""
    path = _Path(_labels_path(run_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"labels": np.asarray(labels, dtype=np.int32)}
    if sample_idx is not None:
        arrays["sample_idx"] = np.asarray(sample_idx, dtype=np.int32)
    np.savez_compressed(path, **arrays)
    return str(path)


def _load_labels(run_id: str):
    """Load the per-cell label artifact, or None if it was never written."""
    path = _Path(_labels_path(run_id))
    if not path.exists():
        return None
    data = np.load(path)
    return {k: data[k] for k in data.files}


def _gatepaths_path(run_id: str) -> str:
    return str(_RUNS_DIR / run_id / "gatepaths.json")


def _labels_for_run(db: SASession, sid: str, run: ClusteringRun):
    """Return (events, channel_names, marker_idx, labels) for a single-file run,
    preferring the persisted label artifact and only re-running FlowSOM for
    legacy runs without one."""
    params = run.params or {}
    path, _fid = _resolve_path(db, sid, params.get("fcs_file_id"))
    events, channel_names, _lbls = _load_cached(path)
    marker_idx = _resolve_marker_idx(channel_names, params.get("markers"))
    saved = _load_labels(run.id)
    if saved is not None and saved.get("labels") is not None and \
            len(saved["labels"]) == events.shape[0]:
        labels = np.asarray(saved["labels"]).astype(int)
    else:
        result = cluster.run_flowsom(
            events, channel_names, marker_idx,
            xdim=int(params.get("xdim", 10)), ydim=int(params.get("ydim", 10)),
            n_clusters=int(params.get("n_clusters", 10)), seed=int(params.get("seed", 42)),
        )
        labels = np.asarray(result["labels"]).astype(int)
    return events, channel_names, marker_idx, labels


def _run_gate_paths(db: SASession, sid: str, run: ClusteringRun) -> dict:
    """Derive (and cache) gate paths for a single-file run, keyed by metacluster id."""
    cache = _Path(_gatepaths_path(run.id))
    if cache.exists():
        with open(cache) as fh:
            return json.load(fh)
    from analysis import gatepaths as _gatepaths

    events, channel_names, marker_idx, labels = _labels_for_run(db, sid, run)
    X = events[:, marker_idx]
    marker_names = [channel_names[i] for i in marker_idx]
    paths = _gatepaths.derive_gate_paths(
        X, labels, marker_names, seed=int((run.params or {}).get("seed", 42))
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    with open(cache, "w") as fh:
        json.dump(paths, fh)
    return paths


# --------------------------------------------------------------------------- request schemas
class ClusteringRequest(BaseModel):
    fcs_file_id: str | None = None
    xdim: int = 10
    ydim: int = 10
    n_clusters: int = 10
    seed: int = 42
    markers: list[str] | None = None


class CohortSampleSpec(BaseModel):
    fcs_file_id: str
    sample_label: str | None = None
    group: str | None = None
    batch: str | None = None
    covariates: dict | None = None


class CohortRequest(BaseModel):
    samples: list[CohortSampleSpec] = Field(default_factory=list)
    xdim: int = 10
    ydim: int = 10
    n_clusters: int = 10
    seed: int = 42
    markers: list[str] | None = None


class SampleTagPatch(BaseModel):
    group: str | None = None
    batch: str | None = None
    covariates: dict | None = None


class PopulationPatch(BaseModel):
    name: str | None = None
    color: str | None = None


class PanelMarkersUpdate(BaseModel):
    markers: dict[str, str] = Field(default_factory=dict)


# --------------------------------------------------------------------------- helpers
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(obj):
    """Coerce numpy scalars/arrays to native python for JSON columns / responses."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _require_session(db: SASession, sid: str) -> SessionModel:
    sess = db.get(SessionModel, sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


def _load_cached(path: str):
    """Load (and cache) the transformed event matrix for ``path``.

    The cache is bounded (LRU-ish by insertion order) so referencing many files
    in a cohort does not grow memory without limit.
    """
    cached = _EVENTS_CACHE.get(path)
    if cached is None:
        cached = analysis_io.load_events(path, transform=True, cofactor=150.0)
        while len(_EVENTS_CACHE) >= _EVENTS_CACHE_MAX:
            _EVENTS_CACHE.pop(next(iter(_EVENTS_CACHE)))
        _EVENTS_CACHE[path] = cached
    return cached


def _resolve_path(db: SASession, sid: str, fcs_file_id: str | None) -> tuple[str, str | None]:
    """Resolve the FCS file path for a run: explicit id -> session's first file -> E1."""
    if fcs_file_id:
        row = db.get(FCSFile, fcs_file_id)
        if row is not None and row.session_id == sid:
            return row.file_path, row.id
    row = db.query(FCSFile).filter(FCSFile.session_id == sid).first()
    if row is not None:
        return row.file_path, row.id
    return _fallback_path(), None


def _resolve_marker_idx(channel_names: list, markers: list | None) -> list:
    """Map requested marker channel names to column indices, else default marker set."""
    if markers:
        by_name = {n: i for i, n in enumerate(channel_names)}
        idx = [by_name[m] for m in markers if m in by_name]
        if idx:
            return idx
    return analysis_io.marker_indices(channel_names, exclude_scatter=True)


def _channel_marker_map(sid: str, channel_names: list, marker_labels: list) -> dict:
    """Channel -> marker map that drives annotation. Starts from the file's own
    $PnS stain labels (when they carry a marker distinct from the channel name),
    then applies saved panel-editor overrides (overrides win). This lets any FCS
    that names its markers -- in $PnN OR $PnS -- auto-annotate without user input."""
    auto: dict[str, str] = {}
    for i, ch in enumerate(channel_names):
        lbl = marker_labels[i] if i < len(marker_labels) else ""
        if lbl and lbl != ch:
            auto[ch] = lbl
    auto.update(PANEL_MARKERS.get(sid, {}))
    return auto


def _run_payload(run: ClusteringRun) -> dict:
    """Full run detail payload (params, umap, populations).

    For cohort runs (``mode == 'cohort'``) the umap rows are 4-tuples
    ``[x, y, metacluster_id, sample_index]``; single-file runs stay 3-tuples.
    """
    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    payload = {
        "id": run.id,
        "status": run.status,
        "params": run.params or {},
        "n_populations": run.n_populations,
        "is_active": run.is_active,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "umap": run.umap or [],
        "populations": _pops_with_axes(pops),
        "mode": getattr(run, "mode", "single") or "single",
        "n_samples": getattr(run, "n_samples", None),
        "shared_markers": getattr(run, "shared_markers", None),
        "dropped_markers": getattr(run, "dropped_markers", None),
        "samples": [
            {
                "id": s.id,
                "sample_index": s.sample_index,
                "sample_label": s.sample_label,
                "group": s.group,
                "batch": s.batch,
                "covariates": s.covariates or {},
                "n_events": s.n_events,
                "n_events_used": s.n_events_used,
            }
            for s in sorted(run.samples, key=lambda s: s.sample_index)
        ],
    }
    return payload


def _pop_payload(p: Population, axes=None) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "metacluster_id": p.metacluster_id,
        "cell_count": p.cell_count,
        "percentage_of_parent": p.percentage_of_parent,
        "median_expression": p.median_expression or {},
        "color": p.color,
        "state_axes": axes or [],
    }


def _pops_with_axes(pops: list) -> list:
    """Payloads for a list of populations, with functional-state axes scored
    across the whole set (requires all populations together to z-score)."""
    axes_list = _state_axes.score_axes(
        [{"median_expression": p.median_expression or {}} for p in pops]
    )
    return [_pop_payload(p, axes_list[i] if i < len(axes_list) else [])
            for i, p in enumerate(pops)]


# --------------------------------------------------------------------------- panel template
@router.get("/sessions/{sid}/panel/template")
def panel_template(sid: str, db: SASession = Depends(get_db)):
    """Marker panel for the config UI: which channels can/should drive clustering."""
    _require_session(db, sid)
    row = db.query(FCSFile).filter(FCSFile.session_id == sid).first()
    path = row.file_path if row is not None else _fallback_path()
    try:
        _events, channel_names, marker_labels = _load_cached(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not read panel: {exc}")

    include_idx = set(analysis_io.marker_indices(channel_names, exclude_scatter=True))
    channels = []
    for i, name in enumerate(channel_names):
        upper = str(name).upper()
        # Time and FSC/SSC are non-biological channels: tag them excluded so the
        # UI groups them with scatter and never clusters on them by default.
        is_scatter = ("FSC" in upper) or ("SSC" in upper) or (upper == "TIME")
        channels.append(
            {
                "channel_name": name,
                "marker_label": marker_labels[i] if i < len(marker_labels) else name,
                "is_scatter": bool(is_scatter),
                "include_in_clustering": i in include_idx,
            }
        )
    return {"channels": channels}


# --------------------------------------------------------------------------- panel markers
@router.get("/sessions/{sid}/panel/markers")
def get_panel_markers(sid: str, fcs_file_id: str | None = None, db: SASession = Depends(get_db)):
    """Channel -> marker map that drives the panel editor / annotation.

    marker precedence: a saved per-session override, else the file's own $PnS
    marker label (only when it differs from the channel name), else "". Reuses the
    same file resolution + marker_indices + scatter/Time logic as panel_template.
    """
    _require_session(db, sid)
    path, _file_id = _resolve_path(db, sid, fcs_file_id)
    try:
        _events, channel_names, marker_labels = _load_cached(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not read panel: {exc}")

    overrides = PANEL_MARKERS.get(sid, {})
    include_idx = set(analysis_io.marker_indices(channel_names, exclude_scatter=True))
    channels = []
    for i, name in enumerate(channel_names):
        upper = str(name).upper()
        is_scatter = ("FSC" in upper) or ("SSC" in upper) or (upper == "TIME")
        label = marker_labels[i] if i < len(marker_labels) else name
        marker = overrides.get(name)
        if not marker:
            marker = str(label) if (label and str(label) != str(name)) else ""
        channels.append(
            {
                "channel_name": name,
                "marker": marker,
                "is_scatter": bool(is_scatter),
                "include_in_clustering": i in include_idx,
            }
        )
    return {"channels": channels}


@router.put("/sessions/{sid}/panel/markers")
def set_panel_markers(sid: str, req: PanelMarkersUpdate, db: SASession = Depends(get_db)):
    """Merge channel->marker overrides into the session map. A blank/empty marker
    clears that channel's override."""
    _require_session(db, sid)
    current = PANEL_MARKERS.setdefault(sid, {})
    for channel, marker in (req.markers or {}).items():
        value = (marker or "").strip()
        if value:
            current[channel] = value
        else:
            current.pop(channel, None)
    return {"ok": True, "n": len([v for v in current.values() if v])}


# --------------------------------------------------------------------------- start clustering
@router.post("/sessions/{sid}/clustering")
def start_clustering(sid: str, req: ClusteringRequest, db: SASession = Depends(get_db)):
    _require_session(db, sid)
    params = req.model_dump()

    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id,
            type="clustering",
            status="pending",
            progress=0,
            message="Queued",
            error=None,
            result=None,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    run_id = str(uuid.uuid4())
    db.add(
        ClusteringRun(
            id=run_id,
            session_id=sid,
            job_id=job_id,
            fcs_file_id=req.fcs_file_id,
            params=params,
            n_populations=None,
            umap=None,
            status="pending",
            created_at=_now(),
            is_active=False,
        )
    )
    db.commit()

    import jobs  # local import: shared ThreadPoolExecutor
    jobs.executor.submit(_run_clustering, job_id, run_id, sid, params)
    return {"job_id": job_id, "clustering_run_id": run_id}


def _update_job(job_id: str, **fields) -> None:
    """Persist a partial Job update using a fresh session (thread-safe)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        if "result" in fields and fields["result"] is not None:
            fields["result"] = _jsonable(fields["result"])
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        db.commit()
    finally:
        db.close()


def _run_clustering(job_id: str, run_id: str, sid: str, params: dict) -> None:
    """Worker: load -> FlowSOM -> UMAP -> persist populations + run. Fresh sessions only."""
    try:
        # 10 ----------------------------------------------------------------- load
        _update_job(job_id, status="running", progress=10, message="Loading", error=None)
        db = SessionLocal()
        try:
            path, fcs_file_id = _resolve_path(db, sid, params.get("fcs_file_id"))
        finally:
            db.close()
        events, channel_names, marker_labels = _load_cached(path)
        marker_idx = _resolve_marker_idx(channel_names, params.get("markers"))

        # 40 ----------------------------------------------------------------- FlowSOM
        _update_job(job_id, progress=40, message="Clustering (FlowSOM)")
        result = cluster.run_flowsom(
            events,
            channel_names,
            marker_idx,
            xdim=int(params.get("xdim", 10)),
            ydim=int(params.get("ydim", 10)),
            n_clusters=int(params.get("n_clusters", 10)),
            seed=int(params.get("seed", 42)),
        )
        labels = np.asarray(result["labels"]).astype(int)
        populations = result["populations"]

        # auto-annotate populations with canonical cell types (editable afterwards).
        # Uses the file's own $PnN/$PnS marker names plus any panel-editor overrides.
        annotations = _annotate.annotate_populations(
            populations,
            channel_to_marker=_channel_marker_map(sid, channel_names, marker_labels),
        )

        # 75 ----------------------------------------------------------------- UMAP
        _update_job(job_id, progress=75, message="UMAP embedding")
        idx, xy = cluster.umap_coords(
            events, marker_idx, subsample=30000, seed=int(params.get("seed", 42))
        )
        sampled_mc = labels[idx]
        umap_list = [
            [float(xy[i, 0]), float(xy[i, 1]), int(sampled_mc[i])]
            for i in range(xy.shape[0])
        ]

        # persist populations + run (fresh session)
        db = SessionLocal()
        try:
            # metacluster_id -> palette index by rank keeps colors stable/sorted.
            for order, pop in enumerate(populations):
                db.add(
                    Population(
                        id=str(uuid.uuid4()),
                        clustering_run_id=run_id,
                        parent_id=None,
                        name=(annotations[order]["label"]
                              or f"Unnamed Population {int(pop['metacluster_id']) + 1}"),
                        metacluster_id=int(pop["metacluster_id"]),
                        cell_count=int(pop["cell_count"]),
                        percentage_of_parent=float(pop["percentage"]),
                        median_expression=_jsonable(pop["median_expression"]),
                        color=palette_color(order),
                        is_manual_gate=False,
                    )
                )

            # deactivate any previously-active run in this session, activate this one.
            for other in (
                db.query(ClusteringRun)
                .filter(ClusteringRun.session_id == sid, ClusteringRun.is_active == True)  # noqa: E712
                .all()
            ):
                other.is_active = False

            # Persist per-cell labels so FlowJo/gate-path export never re-runs FlowSOM.
            labels_file = _save_labels(run_id, labels)

            run = db.get(ClusteringRun, run_id)
            if run is not None:
                run.fcs_file_id = fcs_file_id
                run.n_populations = len(populations)
                run.umap = umap_list
                run.status = "completed"
                run.is_active = True
                run.mode = "single"
                run.labels_path = labels_file
            db.commit()
        finally:
            db.close()

        # 100 ---------------------------------------------------------------- done
        _update_job(
            job_id,
            status="completed",
            progress=100,
            message="Done",
            result={"clustering_run_id": run_id, "n_populations": len(populations)},
        )
    except Exception as exc:  # noqa: BLE001 - report every failure to Job + run rows
        _update_job(job_id, status="failed", message="Failed", error=str(exc))
        db = SessionLocal()
        try:
            run = db.get(ClusteringRun, run_id)
            if run is not None:
                run.status = "failed"
                db.commit()
        finally:
            db.close()


# --------------------------------------------------------------------------- cohort preview
@router.get("/sessions/{sid}/cohort/preview")
def cohort_preview(sid: str, file_ids: str, db: SASession = Depends(get_db)):
    """Given a comma-separated list of file ids, return the shared/dropped markers
    the joint clustering would use. Powers the cohort builder's live preview."""
    _require_session(db, sid)
    ids = [x for x in (file_ids or "").split(",") if x]
    samples = []
    for i, fid in enumerate(ids):
        row = db.get(FCSFile, fid)
        if row is None or row.session_id != sid:
            continue
        samples.append(
            {"file_id": fid, "path": row.file_path, "sample_index": i,
             "sample_label": row.filename}
        )
    if not samples:
        return {"shared_markers": [], "dropped_markers": {}, "n_samples": 0}
    try:
        _keys, labels, _per_file, dropped = _cohort.resolve_shared_markers(samples)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not read panels: {exc}")
    return {
        "shared_markers": labels,
        "dropped_markers": dropped,
        "n_samples": len(samples),
    }


# --------------------------------------------------------------------------- start cohort
@router.post("/sessions/{sid}/cohort")
def start_cohort(sid: str, req: CohortRequest, db: SASession = Depends(get_db)):
    """Kick off a pooled multi-sample clustering run (joint UMAP)."""
    _require_session(db, sid)
    if not req.samples:
        raise HTTPException(status_code=400, detail="a cohort needs at least one sample")

    params = {
        "xdim": req.xdim, "ydim": req.ydim, "n_clusters": req.n_clusters,
        "seed": req.seed, "markers": req.markers,
    }

    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id, type="cohort", status="pending", progress=0,
            message="Queued", error=None, result=None,
            created_at=_now(), updated_at=_now(),
        )
    )
    run_id = str(uuid.uuid4())
    db.add(
        ClusteringRun(
            id=run_id, session_id=sid, job_id=job_id, fcs_file_id=None,
            params=params, n_populations=None, umap=None, status="pending",
            created_at=_now(), is_active=False, mode="cohort",
            n_samples=len(req.samples),
        )
    )
    # One row per sample, tagged with experimental group/covariates. Created now
    # (before the run finishes) so sample tagging is editable immediately.
    for i, spec in enumerate(req.samples):
        row = db.get(FCSFile, spec.fcs_file_id)
        if row is None or row.session_id != sid:
            raise HTTPException(
                status_code=400, detail=f"unknown file: {spec.fcs_file_id}"
            )
        db.add(
            ClusteringRunSample(
                id=str(uuid.uuid4()), clustering_run_id=run_id,
                fcs_file_id=spec.fcs_file_id, sample_index=i,
                sample_label=(spec.sample_label or row.filename),
                group=spec.group, batch=spec.batch, covariates=spec.covariates,
                n_events=int(row.n_events or 0), n_events_used=0,
                created_at=_now(),
            )
        )
    db.commit()

    import jobs  # local import: shared ThreadPoolExecutor
    jobs.executor.submit(_run_cohort_clustering, job_id, run_id, sid, params)
    return {"job_id": job_id, "clustering_run_id": run_id}


def _run_cohort_clustering(job_id: str, run_id: str, sid: str, params: dict) -> None:
    """Worker: pool samples -> one FlowSOM + one UMAP -> per-sample stats. Fresh sessions."""
    try:
        _update_job(job_id, status="running", progress=10, message="Loading samples", error=None)

        # Resolve sample paths from the run's sample rows.
        db = SessionLocal()
        try:
            rows = (
                db.query(ClusteringRunSample)
                .filter(ClusteringRunSample.clustering_run_id == run_id)
                .order_by(ClusteringRunSample.sample_index)
                .all()
            )
            samples = []
            for s in rows:
                f = db.get(FCSFile, s.fcs_file_id)
                if f is None:
                    raise RuntimeError(f"sample file missing: {s.fcs_file_id}")
                samples.append(
                    {"file_id": s.fcs_file_id, "path": f.file_path,
                     "sample_index": s.sample_index, "sample_label": s.sample_label,
                     "run_sample_id": s.id}
                )
        finally:
            db.close()

        # Shared markers + pooled matrix (never holds all raw matrices at once).
        shared_keys, shared_labels, per_file, dropped = _cohort.resolve_shared_markers(
            samples, markers=params.get("markers")
        )
        if not shared_keys:
            raise RuntimeError("samples share no common markers to cluster on")

        _update_job(job_id, progress=30, message="Pooling cells")
        pool = _cohort.build_pool(samples, shared_keys, per_file, seed=int(params.get("seed", 42)))
        pooled_X = pool["pooled_X"]
        sample_idx = pool["sample_idx"]
        umap_idx = pool["umap_idx"]
        per_sample = pool["per_sample"]

        # 55 ----------------------------------------------------------------- FlowSOM
        _update_job(job_id, progress=55, message="Clustering (FlowSOM)")
        marker_idx = list(range(len(shared_labels)))
        result = cluster.run_flowsom(
            pooled_X, shared_labels, marker_idx,
            xdim=int(params.get("xdim", 10)), ydim=int(params.get("ydim", 10)),
            n_clusters=int(params.get("n_clusters", 10)), seed=int(params.get("seed", 42)),
        )
        labels = np.asarray(result["labels"]).astype(int)
        populations = result["populations"]

        annotations = _annotate.annotate_populations(populations, channel_to_marker=None)

        # 80 ----------------------------------------------------------------- UMAP
        _update_job(job_id, progress=80, message="UMAP embedding")
        idx, xy = cluster.umap_coords(
            pooled_X, marker_idx, seed=int(params.get("seed", 42)), preselected_idx=umap_idx
        )
        sampled_mc = labels[idx]
        sampled_sample = sample_idx[idx]
        umap_list = [
            [float(xy[i, 0]), float(xy[i, 1]), int(sampled_mc[i]), int(sampled_sample[i])]
            for i in range(xy.shape[0])
        ]

        metacluster_ids = sorted(np.unique(labels).tolist())
        n_used = {p["sample_index"]: p["n_events_used"] for p in per_sample}
        stats = _cohort.per_sample_stats(
            pooled_X, labels, sample_idx, shared_labels, metacluster_ids, n_used
        )

        labels_file = _save_labels(run_id, labels, sample_idx=sample_idx)

        # persist populations + per-sample stats + run (fresh session)
        db = SessionLocal()
        try:
            mc_to_pop: dict[int, str] = {}
            for order, pop in enumerate(populations):
                pid = str(uuid.uuid4())
                mc_to_pop[int(pop["metacluster_id"])] = pid
                db.add(
                    Population(
                        id=pid, clustering_run_id=run_id, parent_id=None,
                        name=(annotations[order]["label"]
                              or f"Unnamed Population {int(pop['metacluster_id']) + 1}"),
                        metacluster_id=int(pop["metacluster_id"]),
                        cell_count=int(pop["cell_count"]),
                        percentage_of_parent=float(pop["percentage"]),
                        median_expression=_jsonable(pop["median_expression"]),
                        color=palette_color(order), is_manual_gate=False,
                    )
                )

            # Flush populations so their ids exist before the stats rows (which
            # FK to populations.id) are inserted; SQLite enforces FKs immediately.
            db.flush()

            # sample_index -> run_sample_id, and update contributed-cell counts.
            si_to_rs: dict[int, str] = {}
            for s in samples:
                si_to_rs[int(s["sample_index"])] = s["run_sample_id"]
            for ps in per_sample:
                rs = db.get(ClusteringRunSample, si_to_rs[ps["sample_index"]])
                if rs is not None:
                    rs.n_events_used = int(ps["n_events_used"])

            for st in stats:
                pid = mc_to_pop.get(int(st["metacluster_id"]))
                rsid = si_to_rs.get(int(st["sample_index"]))
                if pid is None or rsid is None:
                    continue
                db.add(
                    PopulationSampleStat(
                        id=str(uuid.uuid4()), clustering_run_id=run_id,
                        population_id=pid, run_sample_id=rsid,
                        metacluster_id=int(st["metacluster_id"]),
                        sample_index=int(st["sample_index"]),
                        cell_count=int(st["cell_count"]),
                        percentage_of_sample=float(st["percentage_of_sample"]),
                        median_expression=_jsonable(st["median_expression"]),
                    )
                )

            for other in (
                db.query(ClusteringRun)
                .filter(ClusteringRun.session_id == sid, ClusteringRun.is_active == True)  # noqa: E712
                .all()
            ):
                other.is_active = False

            run = db.get(ClusteringRun, run_id)
            if run is not None:
                run.n_populations = len(populations)
                run.umap = umap_list
                run.status = "completed"
                run.is_active = True
                run.shared_markers = list(shared_labels)
                run.dropped_markers = _jsonable(dropped)
                run.labels_path = labels_file
            db.commit()
        finally:
            db.close()

        _update_job(
            job_id, status="completed", progress=100, message="Done",
            result={"clustering_run_id": run_id, "n_populations": len(populations),
                    "n_samples": len(samples)},
        )
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, status="failed", message="Failed", error=str(exc))
        db = SessionLocal()
        try:
            run = db.get(ClusteringRun, run_id)
            if run is not None:
                run.status = "failed"
                db.commit()
        finally:
            db.close()


# --------------------------------------------------------------------------- list / fetch
@router.get("/sessions/{sid}/clustering")
def list_clustering(sid: str, db: SASession = Depends(get_db)):
    _require_session(db, sid)
    rows = (
        db.query(ClusteringRun)
        .filter(ClusteringRun.session_id == sid)
        .order_by(ClusteringRun.created_at.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "status": r.status,
            "n_populations": r.n_populations,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "is_active": r.is_active,
            "mode": getattr(r, "mode", "single") or "single",
            "n_samples": getattr(r, "n_samples", None),
        }
        for r in rows
    ]


@router.get("/sessions/{sid}/clustering/{rid}")
def get_clustering(sid: str, rid: str, db: SASession = Depends(get_db)):
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    return _run_payload(run)


@router.post("/sessions/{sid}/clustering/{rid}/reannotate")
def reannotate_clustering(sid: str, rid: str):
    """Re-label a run's populations from the CURRENT panel markers, without
    re-clustering. Returns the same shape as GET /clustering/{rid}."""
    db = SessionLocal()
    try:
        run = db.get(ClusteringRun, rid)
        if run is None or run.session_id != sid:
            raise HTTPException(status_code=404, detail="clustering run not found")
        pops = sorted(run.populations, key=lambda p: p.metacluster_id)
        pop_dicts = [
            {
                "metacluster_id": p.metacluster_id,
                "cell_count": p.cell_count,
                "percentage": p.percentage_of_parent,
                "median_expression": p.median_expression or {},
            }
            for p in pops
        ]
        try:
            path, _ = _resolve_path(db, sid, (run.params or {}).get("fcs_file_id"))
            _e, channel_names, marker_labels = _load_cached(path)
            ch_map = _channel_marker_map(sid, channel_names, marker_labels)
        except Exception:  # noqa: BLE001
            ch_map = PANEL_MARKERS.get(sid, {})
        annotations = _annotate.annotate_populations(pop_dicts, channel_to_marker=ch_map)
        for order, p in enumerate(pops):
            label = annotations[order]["label"] if order < len(annotations) else None
            p.name = label or f"Unnamed Population {int(p.metacluster_id) + 1}"
        db.commit()
        db.refresh(run)
        return _run_payload(run)
    finally:
        db.close()


@router.get("/sessions/{sid}/clustering/{rid}/populations")
def get_populations(sid: str, rid: str, db: SASession = Depends(get_db)):
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    return _pops_with_axes(pops)


@router.patch("/sessions/{sid}/clustering/{rid}/populations/{pid}")
def patch_population(
    sid: str, rid: str, pid: str, req: PopulationPatch, db: SASession = Depends(get_db)
):
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    pop = db.get(Population, pid)
    if pop is None or pop.clustering_run_id != rid:
        raise HTTPException(status_code=404, detail="population not found")
    if req.name is not None:
        pop.name = req.name
    if req.color is not None:
        pop.color = req.color
    db.commit()
    db.refresh(pop)
    return _pop_payload(pop)


# --------------------------------------------------------------------------- cohort breakdown
@router.get("/sessions/{sid}/clustering/{rid}/breakdown")
def clustering_breakdown(sid: str, rid: str, db: SASession = Depends(get_db)):
    """population x sample counts/percentages for a cohort run."""
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")

    samples = sorted(run.samples, key=lambda s: s.sample_index)
    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    stats = (
        db.query(PopulationSampleStat)
        .filter(PopulationSampleStat.clustering_run_id == rid)
        .all()
    )
    by_key: dict[tuple, PopulationSampleStat] = {
        (int(s.metacluster_id), int(s.sample_index)): s for s in stats
    }
    return {
        "samples": [
            {"sample_index": s.sample_index, "sample_label": s.sample_label,
             "group": s.group, "batch": s.batch, "n_events_used": s.n_events_used}
            for s in samples
        ],
        "populations": [
            {
                "metacluster_id": p.metacluster_id,
                "name": p.name,
                "color": p.color,
                "per_sample": [
                    {
                        "sample_index": s.sample_index,
                        "cell_count": (by_key.get((p.metacluster_id, s.sample_index)).cell_count
                                       if (p.metacluster_id, s.sample_index) in by_key else 0),
                        "percentage_of_sample": (
                            by_key.get((p.metacluster_id, s.sample_index)).percentage_of_sample
                            if (p.metacluster_id, s.sample_index) in by_key else 0.0),
                    }
                    for s in samples
                ],
            }
            for p in pops
        ],
    }


@router.put("/sessions/{sid}/clustering/{rid}/samples/{sample_id}")
def tag_sample(sid: str, rid: str, sample_id: str, req: SampleTagPatch,
               db: SASession = Depends(get_db)):
    """Update a cohort sample's experimental group / batch / covariate tags."""
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    s = db.get(ClusteringRunSample, sample_id)
    if s is None or s.clustering_run_id != rid:
        raise HTTPException(status_code=404, detail="sample not found")
    if req.group is not None:
        s.group = req.group.strip() or None
    if req.batch is not None:
        s.batch = req.batch.strip() or None
    if req.covariates is not None:
        s.covariates = req.covariates
    db.commit()
    db.refresh(s)
    return {
        "id": s.id, "sample_index": s.sample_index, "sample_label": s.sample_label,
        "group": s.group, "batch": s.batch, "covariates": s.covariates or {},
    }


# --------------------------------------------------------------------------- export
def _tool_versions() -> dict:
    """Best-effort version strings of the wrapped engines for provenance."""
    versions = {}
    for name, mod in (("flowsom", "flowsom"), ("umap-learn", "umap"),
                      ("flowkit", "flowkit"), ("anndata", "anndata"),
                      ("numpy", "numpy"), ("scikit-learn", "sklearn")):
        try:
            m = __import__(mod)
            versions[name] = getattr(m, "__version__", "unknown")
        except Exception:  # noqa: BLE001
            versions[name] = "not-installed"
    return versions


@router.get("/sessions/{sid}/clustering/{rid}/export")
def export_clustering(sid: str, rid: str, db: SASession = Depends(get_db)):
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")

    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    params = run.params or {}
    umap = run.umap or []

    # Stable marker column ordering for the population table.
    marker_names: list[str] = []
    for p in pops:
        for m in (p.median_expression or {}):
            if m not in marker_names:
                marker_names.append(m)

    # ------------------------------------------------------- populations.csv
    pop_buf = _io.StringIO()
    writer = csv.writer(pop_buf)
    writer.writerow(["name", "metacluster_id", "cell_count", "percentage"] + marker_names)
    for p in pops:
        me = p.median_expression or {}
        writer.writerow(
            [p.name, p.metacluster_id, p.cell_count, p.percentage_of_parent]
            + [me.get(m, "") for m in marker_names]
        )

    # ------------------------------------------------------- umap_coordinates.csv
    umap_buf = _io.StringIO()
    uw = csv.writer(umap_buf)
    uw.writerow(["umap_x", "umap_y", "metacluster_id"])
    for row in umap:
        uw.writerow(list(row))

    # ------------------------------------------------------- panel.csv
    panel_buf = _io.StringIO()
    pw = csv.writer(panel_buf)
    pw.writerow(["channel_name", "marker_label", "is_scatter", "include_in_clustering"])
    try:
        tmpl = panel_template(sid, db)
        for ch in tmpl.get("channels", []):
            pw.writerow(
                [
                    ch["channel_name"],
                    ch["marker_label"],
                    ch["is_scatter"],
                    ch["include_in_clustering"],
                ]
            )
    except Exception:  # noqa: BLE001 - panel is best-effort in the bundle
        pass

    # ------------------------------------------------------- session_info.txt
    versions = _tool_versions()
    info_lines = [
        "WakaFlockaFlow - Automated Cell Population Identification",
        "Reproducibility bundle",
        "",
        f"session_id: {sid}",
        f"clustering_run_id: {rid}",
        f"status: {run.status}",
        f"n_populations: {run.n_populations}",
        f"created_at: {run.created_at.isoformat() if run.created_at else ''}",
        "",
        "Parameters:",
    ]
    for k, v in params.items():
        info_lines.append(f"  {k}: {v}")
    info_lines.append("")
    info_lines.append("Engine versions:")
    for k, v in versions.items():
        info_lines.append(f"  {k}: {v}")
    session_info = "\n".join(info_lines) + "\n"

    # ------------------------------------------------------- README_provenance.txt
    readme = (
        "WakaFlockaFlow - Reproducibility Bundle\n"
        "======================================\n\n"
        "This archive documents one automated population-identification run.\n\n"
        "Contents:\n"
        "  populations.csv       - identified populations: name, metacluster id,\n"
        "                          cell count, percentage of total, and median\n"
        "                          expression per clustering marker.\n"
        "  umap_coordinates.csv  - 2D UMAP embedding of a cell subsample, colored by\n"
        "                          metacluster (population) id.\n"
        "  panel.csv             - the marker panel and which channels drove clustering.\n"
        "  session_info.txt      - run parameters and wrapped-engine versions.\n\n"
        "Pipeline: FCS load + arcsinh(cofactor=150) transform -> FlowSOM SOM +\n"
        "metaclustering (Python 'flowsom') -> UMAP embedding (umap-learn).\n\n"
        "Median expression values are in the arcsinh-transformed space. Re-running with\n"
        "the same seed and parameters reproduces these populations.\n"
    )

    # ------------------------------------------------------- zip it up
    zip_buf = _io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("populations.csv", pop_buf.getvalue())
        zf.writestr("umap_coordinates.csv", umap_buf.getvalue())
        zf.writestr("panel.csv", panel_buf.getvalue())
        zf.writestr("session_info.txt", session_info)
        zf.writestr("README_provenance.txt", readme)
    zip_buf.seek(0)

    filename = f"wakaflocka_populations_{rid}.zip"
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- FlowJo export
@router.get("/sessions/{sid}/clustering/{rid}/flowjo")
def flowjo_export(sid: str, rid: str, db: SASession = Depends(get_db)):
    """FlowJo interoperability bundle (.zip): the run's automated populations as
    NAMED gates a user can open directly in FlowJo.

    Re-runs the deterministic clustering with the run's stored params to recover
    the per-cell metacluster labels (they are not persisted), then builds an
    augmented FCS + FlowJo workspace + GatingML 2.0 where each population is a
    named 1-D RectangleGate on a synthetic ``Population`` parameter.
    """
    import shutil
    import tempfile

    from analysis import flowjo as _flowjo

    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")

    if (getattr(run, "mode", "single") or "single") == "cohort":
        raise HTTPException(
            status_code=400,
            detail="FlowJo export is per-sample and not available for cohort runs yet; "
                   "run the sample individually to export its gates.",
        )

    params = run.params or {}

    # Recover the event matrix + per-cell labels. Prefer the persisted labels
    # artifact; only re-run the deterministic clustering for legacy runs that
    # predate label persistence.
    path, _file_id = _resolve_path(db, sid, params.get("fcs_file_id"))
    try:
        events, channel_names, _labels = _load_cached(path)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not read FCS: {exc}")

    marker_idx = _resolve_marker_idx(channel_names, params.get("markers"))
    saved = _load_labels(rid)
    if saved is not None and saved.get("labels") is not None and \
            len(saved["labels"]) == events.shape[0]:
        labels = np.asarray(saved["labels"]).astype(int)
    else:
        result = cluster.run_flowsom(
            events,
            channel_names,
            marker_idx,
            xdim=int(params.get("xdim", 10)),
            ydim=int(params.get("ydim", 10)),
            n_clusters=int(params.get("n_clusters", 10)),
            seed=int(params.get("seed", 42)),
        )
        labels = np.asarray(result["labels"]).astype(int)

    # Populations {metacluster_id, name} from the run, ordered by metacluster id.
    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    populations = [{"metacluster_id": int(p.metacluster_id), "name": p.name} for p in pops]

    # Real marker-threshold gates from the derived gating paths (best effort);
    # falls back to the Population-parameter gate if derivation is unavailable.
    try:
        gate_paths = _run_gate_paths(db, sid, run)
    except Exception:  # noqa: BLE001
        gate_paths = None

    if gate_paths:
        readme = (
            "WakaFlockaFlow - FlowJo Interoperability Export\n"
            "==============================================\n\n"
            "Open workspace.wsp in FlowJo. Each automated population is a named gate\n"
            "defined by real marker thresholds (the gating path that reproduces the\n"
            "cluster), so you can see and adjust the gates on the actual markers.\n\n"
            "Contents:\n"
            "  analyzed.fcs   - the analyzed (arcsinh-transformed) events, plus a\n"
            "                   \"Population\" parameter (metacluster id + 1) for reference.\n"
            "  workspace.wsp  - FlowJo workspace: open this. Each population is a\n"
            "                   RectangleGate on its discriminating markers.\n"
            "  gating.xml     - the same gates as a portable GatingML 2.0 document.\n\n"
            "Gate ranges are in arcsinh-transformed space (cofactor 150), matching the\n"
            "values stored in analyzed.fcs.\n"
        )
    else:
        readme = (
            "WakaFlockaFlow - FlowJo Interoperability Export\n"
            "==============================================\n\n"
            "Open workspace.wsp in FlowJo. Each automated population is a named gate\n"
            "on the \"Population\" parameter of analyzed.fcs.\n\n"
            "Contents:\n"
            "  analyzed.fcs   - the analyzed events with one extra parameter, \"Population\",\n"
            "                   holding this cell's population number (metacluster id + 1).\n"
            "  workspace.wsp  - FlowJo workspace: one named RectangleGate per population\n"
            "                   selecting its cluster on the Population parameter.\n"
            "  gating.xml     - the same gates as a portable GatingML 2.0 document.\n"
        )

    tmpdir = tempfile.mkdtemp(prefix="flowjo_")
    try:
        try:
            paths = _flowjo.build_flowjo_export(
                events, channel_names, labels, populations, tmpdir, gate_paths=gate_paths
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"FlowJo export failed: {exc}")

        zip_buf = _io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(paths["fcs"], "analyzed.fcs")
            zf.write(paths["wsp"], "workspace.wsp")
            zf.write(paths["gatingml"], "gating.xml")
            zf.writestr("README.txt", readme)
        zip_buf.seek(0)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    filename = f"wakaflocka_flowjo_{rid}.zip"
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- gate paths
@router.get("/sessions/{sid}/clustering/{rid}/gatepaths")
def get_gatepaths(sid: str, rid: str, db: SASession = Depends(get_db)):
    """Explainable marker-threshold gating path per population, with a 1-D biaxial
    histogram per gate step and reconstruction quality (precision/recall/F1)."""
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    if (getattr(run, "mode", "single") or "single") == "cohort":
        raise HTTPException(
            status_code=400,
            detail="gate paths are per-sample; run a sample individually to derive them",
        )
    try:
        paths = _run_gate_paths(db, sid, run)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"gate-path derivation failed: {exc}")

    name = {int(p.metacluster_id): p.name for p in run.populations}
    color = {int(p.metacluster_id): p.color for p in run.populations}
    result = []
    for mc_str, gp in paths.items():
        mc = int(mc_str)
        result.append({
            "metacluster_id": mc,
            "name": name.get(mc, f"Population {mc}"),
            "color": color.get(mc, "#888888"),
            **gp,
        })
    result.sort(key=lambda r: (-(r.get("f1") or 0), r["metacluster_id"]))
    return {"populations": result}
