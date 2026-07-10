"""REST API for differential abundance + state testing on a cohort run.

Routes hang off a cohort clustering run:
  POST   /sessions/{sid}/clustering/{rid}/differential          - start a run
  GET    /sessions/{sid}/clustering/{rid}/differential          - list runs
  GET    /sessions/{sid}/clustering/{rid}/differential/{did}    - results (DA+DS)
  GET    /sessions/{sid}/clustering/{rid}/differential/{did}/export - CSV bundle

Long work runs on the shared ThreadPoolExecutor with fresh sessions, mirroring
clustering_api. The default engine is the always-available Python rank-test
fallback; 'diffcyt'/'auto' use the R edgeR+limma recipe when installed.
"""
from __future__ import annotations

import csv
import io as _io
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as SASession

from db import SessionLocal, get_db
from models import Session as SessionModel, Job
from models_cluster import ClusteringRun, Population
from models_diff import DifferentialRun, DAResult, DSResult
from analysis import cohort_matrix, differential

router = APIRouter(prefix="/api/v1")


class DifferentialRequest(BaseModel):
    group_field: str = "group"
    contrast: list[str] | None = None
    covariates: list[str] | None = None
    paired_field: str | None = None
    min_cells: int = 0
    min_samples: int = 1
    engine: str = "python"  # 'python' | 'diffcyt' | 'auto'


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_cohort_run(db: SASession, sid: str, rid: str) -> ClusteringRun:
    sess = db.get(SessionModel, sid)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    run = db.get(ClusteringRun, rid)
    if run is None or run.session_id != sid:
        raise HTTPException(status_code=404, detail="clustering run not found")
    if (getattr(run, "mode", "single") or "single") != "cohort":
        raise HTTPException(
            status_code=400,
            detail="differential testing needs a cohort run (multiple tagged samples)",
        )
    return run


def _update_job(job_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        job.updated_at = _now()
        db.commit()
    finally:
        db.close()


@router.post("/sessions/{sid}/clustering/{rid}/differential")
def start_differential(sid: str, rid: str, req: DifferentialRequest,
                       db: SASession = Depends(get_db)):
    _require_cohort_run(db, sid, rid)
    params = req.model_dump()

    job_id = str(uuid.uuid4())
    db.add(Job(id=job_id, type="differential", status="pending", progress=0,
               message="Queued", error=None, result=None,
               created_at=_now(), updated_at=_now()))
    diff_id = str(uuid.uuid4())
    db.add(DifferentialRun(id=diff_id, clustering_run_id=rid, job_id=job_id,
                           engine=req.engine, params=params, status="pending",
                           created_at=_now()))
    db.commit()

    import jobs
    jobs.executor.submit(_run_differential, job_id, diff_id, rid, params)
    return {"job_id": job_id, "differential_run_id": diff_id}


def _run_differential(job_id: str, diff_id: str, rid: str, params: dict) -> None:
    try:
        _update_job(job_id, status="running", progress=20,
                    message="Assembling matrices", error=None)
        db = SessionLocal()
        try:
            matrices = cohort_matrix.build_matrices(db, rid)
        finally:
            db.close()
        if len(matrices["samples"]) < 2:
            raise RuntimeError("a cohort with at least two samples is required")

        _update_job(job_id, progress=55, message="Testing (DA + DS)")
        result = differential.run_differential(matrices, params)

        db = SessionLocal()
        try:
            for r in result["da"]:
                db.add(DAResult(id=str(uuid.uuid4()), differential_run_id=diff_id,
                                metacluster_id=int(r["metacluster_id"]),
                                log_fc=r.get("log_fc"), p_value=r.get("p_value"),
                                p_adj=r.get("p_adj"), log_cpm=r.get("log_cpm")))
            for r in result["ds"]:
                db.add(DSResult(id=str(uuid.uuid4()), differential_run_id=diff_id,
                                metacluster_id=int(r["metacluster_id"]),
                                marker=r["marker"], log_fc=r.get("log_fc"),
                                p_value=r.get("p_value"), p_adj=r.get("p_adj")))
            drun = db.get(DifferentialRun, diff_id)
            if drun is not None:
                drun.status = "completed"
                drun.engine = result.get("engine", drun.engine)
                drun.notes = result.get("notes") or {}
                drun.message = "Done"
            db.commit()
        finally:
            db.close()

        _update_job(job_id, status="completed", progress=100, message="Done",
                    result={"differential_run_id": diff_id, "engine": result.get("engine")})
    except Exception as exc:  # noqa: BLE001
        _update_job(job_id, status="failed", message="Failed", error=str(exc))
        db = SessionLocal()
        try:
            drun = db.get(DifferentialRun, diff_id)
            if drun is not None:
                drun.status = "failed"
                drun.message = str(exc)
                db.commit()
        finally:
            db.close()


@router.get("/sessions/{sid}/clustering/{rid}/differential")
def list_differential(sid: str, rid: str, db: SASession = Depends(get_db)):
    _require_cohort_run(db, sid, rid)
    rows = (db.query(DifferentialRun)
            .filter(DifferentialRun.clustering_run_id == rid)
            .order_by(DifferentialRun.created_at.desc()).all())
    return [{"id": r.id, "status": r.status, "engine": r.engine,
             "params": r.params or {}, "notes": r.notes or {},
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


@router.get("/sessions/{sid}/clustering/{rid}/differential/{did}")
def get_differential(sid: str, rid: str, did: str, db: SASession = Depends(get_db)):
    _require_cohort_run(db, sid, rid)
    drun = db.get(DifferentialRun, did)
    if drun is None or drun.clustering_run_id != rid:
        raise HTTPException(status_code=404, detail="differential run not found")

    pops = db.query(Population).filter(Population.clustering_run_id == rid).all()
    name = {int(p.metacluster_id): p.name for p in pops}
    color = {int(p.metacluster_id): p.color for p in pops}

    da = sorted(drun.da_results,
                key=lambda r: (r.p_adj if r.p_adj is not None else 1.0))
    ds = drun.ds_results
    return {
        "id": drun.id, "status": drun.status, "engine": drun.engine,
        "params": drun.params or {}, "notes": drun.notes or {},
        "da": [{"metacluster_id": r.metacluster_id,
                "name": name.get(r.metacluster_id, f"Population {r.metacluster_id}"),
                "color": color.get(r.metacluster_id, "#888888"),
                "log_fc": r.log_fc, "p_value": r.p_value, "p_adj": r.p_adj,
                "log_cpm": r.log_cpm} for r in da],
        "ds": [{"metacluster_id": r.metacluster_id, "marker": r.marker,
                "log_fc": r.log_fc, "p_value": r.p_value, "p_adj": r.p_adj}
               for r in ds],
    }


@router.get("/sessions/{sid}/clustering/{rid}/differential/{did}/export")
def export_differential(sid: str, rid: str, did: str, db: SASession = Depends(get_db)):
    _require_cohort_run(db, sid, rid)
    drun = db.get(DifferentialRun, did)
    if drun is None or drun.clustering_run_id != rid:
        raise HTTPException(status_code=404, detail="differential run not found")

    pops = db.query(Population).filter(Population.clustering_run_id == rid).all()
    name = {int(p.metacluster_id): p.name for p in pops}

    da_buf = _io.StringIO()
    dw = csv.writer(da_buf)
    dw.writerow(["metacluster_id", "population", "log_fc", "p_value", "p_adj", "log_cpm"])
    for r in sorted(drun.da_results, key=lambda r: (r.p_adj if r.p_adj is not None else 1.0)):
        dw.writerow([r.metacluster_id, name.get(r.metacluster_id, ""),
                     r.log_fc, r.p_value, r.p_adj, r.log_cpm])

    ds_buf = _io.StringIO()
    sw = csv.writer(ds_buf)
    sw.writerow(["metacluster_id", "population", "marker", "log_fc", "p_value", "p_adj"])
    for r in drun.ds_results:
        sw.writerow([r.metacluster_id, name.get(r.metacluster_id, ""), r.marker,
                     r.log_fc, r.p_value, r.p_adj])

    readme = (
        "WakaFlockaFlow - Differential Analysis Export\n"
        "=============================================\n\n"
        f"engine: {drun.engine}\n"
        f"parameters: {drun.params}\n"
        f"notes: {drun.notes}\n\n"
        "da_results.csv - differential abundance per population (log fold change,\n"
        "                 p-value, BH-adjusted p-value, log-CPM).\n"
        "ds_results.csv - differential state per (population, marker). Effect sizes\n"
        "                 for the Python engine are in arcsinh-transformed space.\n"
    )

    zip_buf = _io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("da_results.csv", da_buf.getvalue())
        zf.writestr("ds_results.csv", ds_buf.getvalue())
        zf.writestr("README.txt", readme)
    zip_buf.seek(0)
    return StreamingResponse(
        zip_buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="wakaflocka_differential_{did}.zip"'},
    )
