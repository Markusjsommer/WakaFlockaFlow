"""FastAPI app for WakaFlockaFlow - automated cell-population identification.

Point at an FCS file -> arcsinh transform -> FlowSOM clustering + UMAP -> named cell
populations with count/percentage/median-marker tables -> reproducibility export.

All routes live under /api/v1. Long-running work (clustering, export) runs in the
ThreadPoolExecutor in jobs.py; handlers return {"job_id"} immediately and the frontend
polls GET /api/v1/jobs/{id} every 2s. In the packaged Docker image the built SPA is served
by this same process (WAKAFLOCKA_STATIC); in dev the Vite server proxies to it. The optional
synthetic batch-correction routes remain as a pipeline self-test, not the product.
"""

import os
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as SASession

from db import engine, SessionLocal, Base, get_db
from models import Session as SessionModel, FCSFile, Job, BatchCorrectionRun
import models_cluster  # noqa: F401 - registers ClusteringRun/Population on Base.metadata
import models_diff  # noqa: F401 - registers DifferentialRun/DAResult/DSResult on Base.metadata
from clustering_api import router as clustering_router
from differential_api import router as differential_router
import unmix_api
from analysis import io as analysis_io
import jobs

# --------------------------------------------------------------------------- paths
REPO_ROOT = Path(__file__).resolve().parent.parent
# Runtime state + bundled demo are env-overridable so a pip/conda install can
# point them at a user-writable dir and the packaged sample data respectively
# (the console launcher sets these); unset falls back to the repo layout.
DATA_DIR = Path(os.environ.get("WAKAFLOCKA_DATA") or (REPO_ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
JOBS_DIR = DATA_DIR / "jobs"
EXPORTS_DIR = DATA_DIR / "exports"
_SAMPLE_ROOT = Path(os.environ.get("WAKAFLOCKA_SAMPLE_DATA") or (REPO_ROOT / "sample_data"))
E1_PATH = REPO_ROOT / "PBMC_40color_E1_UNMIXED.fcs"
DEMO_DIR = _SAMPLE_ROOT / "spectral_pbmc"  # bundled permissive demo (Artistic-2.0)
DIFF_DEMO_DIR = _SAMPLE_ROOT / "differential_demo"  # synthetic cohort for the differential demo

# In-memory per-session transform config (single-process prototype).
TRANSFORMS: dict[str, dict] = {}

# Cache marker lists per FCS path (reading 132k events per request is wasteful).
_MARKERS_CACHE: dict[str, list[str]] = {}


# --------------------------------------------------------------------------- request schemas
# Prefer schemas.py definitions when the concurrent slice provides matching names; otherwise
# fall back to these contract-derived models so this slice always imports/runs standalone.
class _TransformRequest(BaseModel):
    method: str = "arcsinh"
    params: dict = Field(default_factory=lambda: {"cofactor": 150.0})


class _BatchCorrectionRequest(BaseModel):
    n_batches: int = 2
    drift_markers: list[str] = Field(default_factory=list)
    drift_a: float = 1.3
    drift_b: float = 0.2
    nClus: int = 10
    nQ: int = 101
    seed: int = 42
    engine: str = "cytonorm"


class _SessionCreate(BaseModel):
    name: str = "session"


class _ExportRequest(BaseModel):
    run_id: str | None = None
    batch_correction_run_id: str | None = None


try:  # pragma: no cover - prefer shared schemas if the schemas slice defines them
    import schemas as _schemas

    TransformRequest = getattr(_schemas, "TransformRequest", _TransformRequest)
    BatchCorrectionRequest = getattr(_schemas, "BatchCorrectionRequest", _BatchCorrectionRequest)
    SessionCreate = getattr(_schemas, "SessionCreate", _SessionCreate)
    ExportRequest = getattr(_schemas, "ExportRequest", _ExportRequest)
except Exception:  # noqa: BLE001
    TransformRequest = _TransformRequest
    BatchCorrectionRequest = _BatchCorrectionRequest
    SessionCreate = _SessionCreate
    ExportRequest = _ExportRequest


# --------------------------------------------------------------------------- helpers
def _now():
    return datetime.now(timezone.utc)


_META_CACHE: dict[str, tuple] = {}


def _meta(path):
    """(n_events, n_channels, has_markers) for an FCS file, cached per path.
    has_markers = the file's channels/$PnS labels resolve to canonical markers
    (CD3, CD19, ...), i.e. auto cell-type annotation can run on it."""
    key = str(path)
    if key in _META_CACHE:
        return _META_CACHE[key]
    try:
        from analysis.annotate import normalize_marker
        events, channel_names, marker_labels = analysis_io.load_events(key, transform=False)
        labels = marker_labels if marker_labels else []
        has_markers = any(
            normalize_marker(channel_names[i])
            or (i < len(labels) and normalize_marker(labels[i]))
            for i in range(len(channel_names))
        )
        info = (int(events.shape[0]), int(events.shape[1]), bool(has_markers))
    except Exception:  # noqa: BLE001
        info = (0, 0, False)
    _META_CACHE[key] = info
    return info


def _probe(path: Path):
    """Return (n_events, n_channels) for an FCS file, best-effort."""
    ne, nc, _ = _meta(path)
    return ne, nc


def _require_session(db: SASession, sid: str) -> SessionModel:
    sess = db.get(SessionModel, sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


def _bootstrap():
    """Create data dirs + tables, ensure a default session, register the E1 file."""
    for directory in (DATA_DIR, UPLOAD_DIR, JOBS_DIR, EXPORTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)
    # create_all adds new tables but never new columns to an existing table;
    # backfill the cohort columns on legacy clustering_runs rows.
    models_cluster.ensure_columns(engine)

    db = SessionLocal()
    try:
        sess = db.query(SessionModel).first()
        if sess is None:
            sess = SessionModel(id=str(uuid.uuid4()), name="default", created_at=_now())
            db.add(sess)
            db.commit()
            db.refresh(sess)

        if E1_PATH.exists():
            already = (
                db.query(FCSFile)
                .filter(FCSFile.session_id == sess.id, FCSFile.filename == E1_PATH.name)
                .first()
            )
            if already is None:
                n_events, n_channels = _probe(E1_PATH)
                if n_events == 0:  # known dimensions of the bundled E1 acquisition
                    n_events, n_channels = 132360, 47
                db.add(
                    FCSFile(
                        id=str(uuid.uuid4()),
                        session_id=sess.id,
                        filename=E1_PATH.name,
                        file_path=str(E1_PATH),
                        n_events=n_events,
                        n_channels=n_channels,
                        uploaded_at=_now(),
                    )
                )
                db.commit()

        # Register the bundled permissive demo data (flowSpecs, Artistic-2.0) so a
        # fresh clone can analyze something out of the box with no user files present.
        if DEMO_DIR.is_dir():
            for entry in sorted(DEMO_DIR.glob("*.fcs")):
                fpath = str(entry.resolve())
                exists = (
                    db.query(FCSFile)
                    .filter(FCSFile.session_id == sess.id, FCSFile.file_path == fpath)
                    .first()
                )
                if exists is not None:
                    continue
                n_events, n_channels = _probe(entry)
                db.add(
                    FCSFile(
                        id=str(uuid.uuid4()),
                        session_id=sess.id,
                        filename="[demo] " + entry.name,
                        file_path=fpath,
                        n_events=n_events,
                        n_channels=n_channels,
                        uploaded_at=_now(),
                    )
                )
            db.commit()

        # Register the synthetic differential-demo cohort (clearly labelled SYN_*)
        # so the differential workflow can be demoed out of the box. Not real data.
        if DIFF_DEMO_DIR.is_dir():
            for entry in sorted(DIFF_DEMO_DIR.glob("*.fcs")):
                fpath = str(entry.resolve())
                exists = (
                    db.query(FCSFile)
                    .filter(FCSFile.session_id == sess.id, FCSFile.file_path == fpath)
                    .first()
                )
                if exists is not None:
                    continue
                n_events, n_channels = _probe(entry)
                db.add(
                    FCSFile(
                        id=str(uuid.uuid4()),
                        session_id=sess.id,
                        filename=entry.name,
                        file_path=fpath,
                        n_events=n_events,
                        n_channels=n_channels,
                        uploaded_at=_now(),
                    )
                )
            db.commit()

        # Register any *.fcs dropped into WAKAFLOCKA_FCS_DIR (Docker bind-mount) as
        # files of the default session, in addition to the bundled E1 acquisition.
        fcs_dir = os.environ.get("WAKAFLOCKA_FCS_DIR")
        if fcs_dir and os.path.isdir(fcs_dir):
            for entry in sorted(Path(fcs_dir).glob("*.fcs")):
                fpath = str(entry.resolve())
                exists = (
                    db.query(FCSFile)
                    .filter(FCSFile.session_id == sess.id, FCSFile.file_path == fpath)
                    .first()
                )
                if exists is not None:
                    continue
                n_events, n_channels = _probe(entry)
                db.add(
                    FCSFile(
                        id=str(uuid.uuid4()),
                        session_id=sess.id,
                        filename=entry.name,
                        file_path=fpath,
                        n_events=n_events,
                        n_channels=n_channels,
                        uploaded_at=_now(),
                    )
                )
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap()
    yield


app = FastAPI(title="WakaFlockaFlow", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api/v1")


# --------------------------------------------------------------------------- capabilities
@router.get("/capabilities")
def capabilities():
    """What this deployment can actually run. R-based features (spectral unmixing
    via AutoSpectral, the diffcyt differential engine) are only available where R
    is reachable, so the UI gates on this instead of offering steps that will fail.
    """
    from analysis import r_engine

    return {
        "r_mode": r_engine.R_MODE,
        "unmix": r_engine.engine_available("run_unmix.R"),
        "diffcyt": r_engine.engine_available("run_diffcyt.R"),
        # These are pure-Python and always available.
        "population_id": True,
        "cohort": True,
        "differential_python": True,
        "functional_state": True,
        "gate_paths": True,
        "flowjo_export": True,
    }


# --------------------------------------------------------------------------- sessions / files
@router.post("/sessions")
def create_session(payload: SessionCreate | None = None, db: SASession = Depends(get_db)):
    name = payload.name if payload is not None else "session"
    sid = str(uuid.uuid4())
    db.add(SessionModel(id=sid, name=name, created_at=_now()))
    db.commit()
    return {"session_id": sid}


@router.get("/default-session")
def default_session(db: SASession = Depends(get_db)):
    """The bootstrap session that owns the bundled demo + WAKAFLOCKA_FCS_DIR files.
    The single-user UI reuses this so registered files show up on load."""
    sess = db.query(SessionModel).order_by(SessionModel.created_at.asc()).first()
    if sess is None:
        sess = SessionModel(id=str(uuid.uuid4()), name="default", created_at=_now())
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return {"session_id": sess.id}


@router.post("/sessions/{sid}/files")
async def upload_files(
    sid: str,
    files: list[UploadFile] = File(...),
    db: SASession = Depends(get_db),
):
    _require_session(db, sid)
    updir = UPLOAD_DIR / sid
    updir.mkdir(parents=True, exist_ok=True)

    out = []
    for upload in files:
        dest = updir / upload.filename
        with open(dest, "wb") as fh:
            shutil.copyfileobj(upload.file, fh)
        n_events, n_channels = _probe(dest)
        fid = str(uuid.uuid4())
        db.add(
            FCSFile(
                id=fid,
                session_id=sid,
                filename=upload.filename,
                file_path=str(dest),
                n_events=n_events,
                n_channels=n_channels,
                uploaded_at=_now(),
            )
        )
        out.append({"id": fid, "filename": upload.filename,
                    "n_events": n_events, "n_channels": n_channels})
    db.commit()
    return out


@router.get("/sessions/{sid}/files")
def list_files(sid: str, db: SASession = Depends(get_db)):
    _require_session(db, sid)
    rows = db.query(FCSFile).filter(FCSFile.session_id == sid).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "n_events": r.n_events,
            "n_channels": r.n_channels,
            "has_markers": _meta(r.file_path)[2],
        }
        for r in rows
    ]


@router.get("/sessions/{sid}/markers")
def list_markers(sid: str, db: SASession = Depends(get_db)):
    """Fluorophore-marker channel names for the panel (drives the UI marker picker)."""
    _require_session(db, sid)
    row = db.query(FCSFile).filter(FCSFile.session_id == sid).first()
    path = row.file_path if row is not None else str(E1_PATH)
    if path in _MARKERS_CACHE:
        return {"markers": _MARKERS_CACHE[path]}
    try:
        _events, channel_names, _labels = analysis_io.load_events(path, transform=False)
        idx = analysis_io.marker_indices(channel_names)
        markers = [channel_names[i] for i in idx]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"could not read panel: {exc}")
    _MARKERS_CACHE[path] = markers
    return {"markers": markers}


@router.put("/sessions/{sid}/transform")
def set_transform(sid: str, req: TransformRequest, db: SASession = Depends(get_db)):
    _require_session(db, sid)
    TRANSFORMS[sid] = req.model_dump()
    return {"ok": True}


# --------------------------------------------------------------------------- batch correction
@router.post("/sessions/{sid}/batch-correction")
def start_batch_correction(sid: str, req: BatchCorrectionRequest, db: SASession = Depends(get_db)):
    _require_session(db, sid)
    params = req.model_dump()

    transform = TRANSFORMS.get(sid)
    if transform:
        cofactor = (transform.get("params") or {}).get("cofactor")
        if cofactor is not None:
            params["cofactor"] = float(cofactor)

    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id,
            type="batch_correction",
            status="pending",
            progress=0,
            message="Queued",
            error=None,
            result=None,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.commit()

    jobs.submit_batch_correction(job_id, sid, params)
    return {"job_id": job_id}


@router.get("/sessions/{sid}/batch-correction/{rid}")
def get_batch_correction(sid: str, rid: str, db: SASession = Depends(get_db)):
    run = db.get(BatchCorrectionRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="batch-correction run not found")

    emd_before = run.emd_before or {}
    emd_after = run.emd_after or {}
    per_marker = {
        marker: {"before": emd_before.get(marker), "after": emd_after.get(marker)}
        for marker in emd_before
    }

    return {
        "id": run.id,
        "status": run.status,
        "synthetic": True,
        "banner": jobs.BANNER,
        "mean_emd_before": run.mean_emd_before,
        "mean_emd_after": run.mean_emd_after,
        "reduction_pct": run.reduction_pct,
        "per_marker": per_marker,
        "umap_before": run.umap_before or [],
        "umap_after": run.umap_after or [],
        "injected": run.injected or {},
    }


# --------------------------------------------------------------------------- export
@router.post("/sessions/{sid}/export")
def start_export(sid: str, req: ExportRequest | None = None, db: SASession = Depends(get_db)):
    _require_session(db, sid)

    run_id = None
    if req is not None:
        run_id = req.run_id or req.batch_correction_run_id
    if run_id is None:
        latest = (
            db.query(BatchCorrectionRun)
            .filter(BatchCorrectionRun.session_id == sid)
            .order_by(BatchCorrectionRun.created_at.desc())
            .first()
        )
        if latest is not None:
            run_id = latest.id

    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id,
            type="export",
            status="pending",
            progress=0,
            message="Queued",
            error=None,
            result=None,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    db.commit()

    jobs.submit_export(job_id, sid, run_id)
    return {"job_id": job_id}


@router.get("/sessions/{sid}/export/{bid}/download")
def download_export(sid: str, bid: str, db: SASession = Depends(get_db)):
    zip_path = EXPORTS_DIR / f"{bid}.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="export not ready")
    return FileResponse(
        str(zip_path),
        media_type="application/zip",
        filename=f"wakaflocka_export_{bid}.zip",
    )


# --------------------------------------------------------------------------- jobs poll
@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: SASession = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "result": job.result,
    }


app.include_router(router)
app.include_router(clustering_router)
app.include_router(differential_router)
app.include_router(unmix_api.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "WakaFlockaFlow"}


# Serve the built frontend SPA when a static bundle is provided (Docker: one port for
# API + UI). Mounted AFTER all routers so /api/v1 still resolves; guarded by env so dev
# (uvicorn + vite) is unaffected.
_static_dir = os.environ.get("WAKAFLOCKA_STATIC")
if _static_dir and os.path.isdir(_static_dir):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
