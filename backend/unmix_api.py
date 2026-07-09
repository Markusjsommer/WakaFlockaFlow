"""REST API for spectral unmixing (v2).

Raw detector FCS + single-stain controls -> AutoSpectral (R) -> a per-marker unmixed
FCS that is registered as a session file and can then feed the existing population-ID
pipeline (FlowSOM/UMAP).

The unmix job runs on the shared ``jobs.executor`` ThreadPoolExecutor; each DB write
inside the worker uses a FRESH ``SessionLocal()`` (worker threads must never share the
request-scoped session). The frontend polls GET /api/v1/sessions/{sid}/unmix/{job_id}.
"""
from __future__ import annotations

import os
import re
import glob
import uuid
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as SASession

from db import SessionLocal, get_db
from models import Session as SessionModel, FCSFile, Job
from analysis import io as analysis_io
from analysis import r_engine, unmix
import jobs

# --------------------------------------------------------------------------- paths
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CONTROLS_DIR = REPO_ROOT / "sample_data" / "spectral_pbmc" / "controls"

# Session files auto-picked as controls when the caller supplies no explicit ids.
_CONTROL_NAME_RE = re.compile(r"bead|unstained|control|dead", re.IGNORECASE)

router = APIRouter(prefix="/api/v1")


# --------------------------------------------------------------------------- schemas
class UnmixRequest(BaseModel):
    raw_file_id: str
    control_source: str = "bundled"  # "bundled" | "session"
    control_file_ids: list[str] | None = None
    cytometer: str = "aurora"


# --------------------------------------------------------------------------- helpers
def _now():
    return datetime.now(timezone.utc)


def _update(job_id: str, **fields):
    """Persist a partial Job update using a fresh session (thread-safe)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        db.commit()
    finally:
        db.close()


def _probe(path: str):
    """Best-effort (n_events, n_channels) for an FCS file."""
    try:
        events, _channels, _labels = analysis_io.load_events(path, transform=False)
        return int(events.shape[0]), int(events.shape[1])
    except Exception:  # noqa: BLE001
        return 0, 0


def _bundled_controls() -> list[str]:
    return sorted(str(p) for p in CONTROLS_DIR.glob("*.fcs"))


def _require_session(db: SASession, sid: str) -> SessionModel:
    sess = db.get(SessionModel, sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return sess


# --------------------------------------------------------------------------- worker
def _run_unmix(job_id: str, sid: str, raw_file_id: str, control_source: str,
               control_file_ids: list | None, params: dict):
    try:
        # Resolve raw file + control paths from the DB (fresh session on this thread).
        db = SessionLocal()
        try:
            raw = db.get(FCSFile, raw_file_id)
            if raw is None or raw.session_id != sid:
                raise RuntimeError("raw file not found in session")
            raw_path = raw.file_path
            raw_name = raw.filename

            if control_source == "session":
                if control_file_ids:
                    rows = (
                        db.query(FCSFile)
                        .filter(FCSFile.session_id == sid,
                                FCSFile.id.in_(list(control_file_ids)))
                        .all()
                    )
                    controls = [r.file_path for r in rows]
                else:
                    rows = db.query(FCSFile).filter(FCSFile.session_id == sid).all()
                    controls = [
                        r.file_path for r in rows
                        if _CONTROL_NAME_RE.search(r.filename or "")
                    ]
            else:
                controls = _bundled_controls()
        finally:
            db.close()

        if not controls:
            raise RuntimeError("no control files resolved for unmixing")

        # 10 --------------------------------------------------------------- stage inputs
        _update(job_id, status="running", progress=10,
                message="Preparing controls", error=None)
        jobdir = os.path.join(str(DATA_DIR), "jobs", job_id)
        indir = os.path.join(jobdir, "input")
        os.makedirs(indir, exist_ok=True)
        unmix.setup_unmix_job(indir, raw_path, controls, params)

        # 40 --------------------------------------------------------------- unmix (R)
        _update(job_id, progress=40, message="Unmixing (AutoSpectral)")
        outdir = r_engine.run_r_job("run_unmix.R", jobdir)

        # 90 --------------------------------------------------------------- register file
        _update(job_id, progress=90, message="Registering unmixed file")
        unmixed_src = unmix.collect_unmixed(outdir)

        unmixed_root = os.path.join(str(DATA_DIR), "unmixed")
        os.makedirs(unmixed_root, exist_ok=True)
        dest = os.path.join(unmixed_root, f"{job_id}.fcs")
        shutil.copyfile(unmixed_src, dest)

        n_events, n_channels = _probe(dest)
        unmixed_filename = "[unmixed] " + raw_name

        new_id = str(uuid.uuid4())
        db = SessionLocal()
        try:
            db.add(
                FCSFile(
                    id=new_id,
                    session_id=sid,
                    filename=unmixed_filename,
                    file_path=dest,
                    n_events=n_events,
                    n_channels=n_channels,
                    uploaded_at=_now(),
                )
            )
            db.commit()
        finally:
            db.close()

        # 100 -------------------------------------------------------------- done
        _update(
            job_id,
            status="completed",
            progress=100,
            message="Done",
            result={"unmixed_file_id": new_id, "unmixed_filename": unmixed_filename},
        )
    except Exception as exc:  # noqa: BLE001 - report every failure to the Job row
        _update(job_id, status="failed", message="Failed", error=str(exc))


# --------------------------------------------------------------------------- routes
@router.get("/sessions/{sid}/unmix/controls")
def unmix_controls(sid: str, db: SASession = Depends(get_db)):
    """Names of the bundled demo controls, so the UI can offer them out of the box."""
    _require_session(db, sid)
    names = [os.path.basename(p) for p in _bundled_controls()]
    return {"bundled": names, "count": len(names)}


@router.post("/sessions/{sid}/unmix")
def start_unmix(sid: str, req: UnmixRequest, db: SASession = Depends(get_db)):
    _require_session(db, sid)

    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id,
            type="unmix",
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

    params = {"cytometer": req.cytometer}
    jobs.executor.submit(
        _run_unmix, job_id, sid, req.raw_file_id, req.control_source,
        req.control_file_ids, params,
    )
    return {"job_id": job_id}


@router.get("/sessions/{sid}/unmix/{job_id}")
def get_unmix(sid: str, job_id: str, db: SASession = Depends(get_db)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
        "result": job.result,
    }
