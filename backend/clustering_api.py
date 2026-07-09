"""REST API for automated cell population identification.

Endpoints under /api/v1 that drive the population-ID workflow:
  * panel/template   - marker panel for the config UI (which channels to cluster on)
  * clustering (POST)- kick off a FlowSOM + UMAP run on a worker thread; returns {job_id}
  * clustering (GET) - list / fetch runs and their identified populations
  * populations PATCH- rename / recolor a population
  * export           - reproducibility bundle (.zip: CSVs + provenance)

Long-running work is submitted to ``jobs.executor`` (the shared ThreadPoolExecutor) and
each DB write inside a worker uses a FRESH ``SessionLocal()`` — worker threads must never
share the request-scoped session. The frontend polls GET /api/v1/jobs/{id} for progress.
"""
from __future__ import annotations

import csv
import io as _io
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
from models_cluster import ClusteringRun, Population, palette_color
from analysis import io as analysis_io
from analysis import cluster

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
_EVENTS_CACHE: dict[str, tuple] = {}

router = APIRouter(prefix="/api/v1")


# --------------------------------------------------------------------------- request schemas
class ClusteringRequest(BaseModel):
    fcs_file_id: str | None = None
    xdim: int = 10
    ydim: int = 10
    n_clusters: int = 10
    seed: int = 42
    markers: list[str] | None = None


class PopulationPatch(BaseModel):
    name: str | None = None
    color: str | None = None


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
    """Load (and cache) the transformed event matrix for ``path``."""
    cached = _EVENTS_CACHE.get(path)
    if cached is None:
        cached = analysis_io.load_events(path, transform=True, cofactor=150.0)
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


def _run_payload(run: ClusteringRun) -> dict:
    """Full run detail payload (params, umap, populations)."""
    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    return {
        "id": run.id,
        "status": run.status,
        "params": run.params or {},
        "n_populations": run.n_populations,
        "is_active": run.is_active,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "umap": run.umap or [],
        "populations": [_pop_payload(p) for p in pops],
    }


def _pop_payload(p: Population) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "metacluster_id": p.metacluster_id,
        "cell_count": p.cell_count,
        "percentage_of_parent": p.percentage_of_parent,
        "median_expression": p.median_expression or {},
        "color": p.color,
    }


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
        events, channel_names, _labels = _load_cached(path)
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
                        name=f"Population {int(pop['metacluster_id']) + 1}",
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

            run = db.get(ClusteringRun, run_id)
            if run is not None:
                run.fcs_file_id = fcs_file_id
                run.n_populations = len(populations)
                run.umap = umap_list
                run.status = "completed"
                run.is_active = True
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
        }
        for r in rows
    ]


@router.get("/sessions/{sid}/clustering/{rid}")
def get_clustering(sid: str, rid: str, db: SASession = Depends(get_db)):
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    return _run_payload(run)


@router.get("/sessions/{sid}/clustering/{rid}/populations")
def get_populations(sid: str, rid: str, db: SASession = Depends(get_db)):
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    pops = sorted(run.populations, key=lambda p: p.metacluster_id)
    return [_pop_payload(p) for p in pops]


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
        "WakaFlakaFlow — Automated Cell Population Identification",
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
        "WakaFlakaFlow — Reproducibility Bundle\n"
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

    filename = f"wakaflaka_populations_{rid}.zip"
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
