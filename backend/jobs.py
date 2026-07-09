"""ThreadPoolExecutor pipeline glue for WakaFlakaFlow.

Owns the long-running work behind the REST layer:
  * submit_batch_correction -> synthetic drift injection -> CytoNorm/ComBat -> EMD -> UMAP
  * submit_export           -> zip corrected FCS + emd.csv + injected.json + warning

Every DB write uses a FRESH SQLAlchemy session (jobs run on worker threads, so we never
share the request-scoped session). Progress is written to the Job row so the frontend can
poll GET /api/v1/jobs/{id} every 2s.
"""

import os
import json
import uuid
import zipfile
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from db import SessionLocal
from models import Job, BatchCorrectionRun
from analysis import io, synth, emd, embed, cytonorm

# --------------------------------------------------------------------------- paths / constants
REPO_ROOT = Path(__file__).resolve().parent.parent
E1_PATH = str(REPO_ROOT / "PBMC_40color_E1_UNMIXED.fcs")
DATA_DIR = REPO_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
EXPORTS_DIR = DATA_DIR / "exports"

# Mandatory integrity banner — surfaced on every screen and in every export.
BANNER = "SYNTHETIC BATCH EFFECT — mechanism demo, not real multi-batch data"

SYNTHETIC_WARNING = (
    "SYNTHETIC BATCH EFFECT — READ THIS FIRST\n"
    "========================================\n\n"
    "The results in this export were produced by INJECTING a known, artificial batch\n"
    "effect (a monotone per-marker drift x' = a*x + b) into a SINGLE real acquisition\n"
    "(PBMC_40color_E1_UNMIXED.fcs) and then correcting it. There is only ONE real\n"
    "acquisition = ONE batch, so real multi-batch correction cannot run on it.\n\n"
    "This is a legitimate way to VALIDATE a normalization pipeline (recover a known\n"
    "injected drift) and it exercises the entire real stack (FCS I/O -> CytoNorm/ComBat\n"
    "-> EMD -> UMAP). It is NOT a real multi-batch biological result and must never be\n"
    "presented as one. See injected.json for the exact drift parameters that were applied.\n"
)

executor = ThreadPoolExecutor(max_workers=2)


# --------------------------------------------------------------------------- helpers
def _now():
    return datetime.now(timezone.utc)


def _jsonable(obj):
    """Recursively coerce numpy scalars/arrays to native python so JSON columns serialize."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def _update(job_id, **fields):
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


def _resolve_drift_idx(names, channel_names, marker_labels):
    """Map requested drift-marker names to column indices (by $PnN then $PnS)."""
    if not names:
        return None
    by_channel = {n: i for i, n in enumerate(channel_names)}
    by_label = {n: i for i, n in enumerate(marker_labels)}
    idx = []
    for name in names:
        if name in by_channel:
            idx.append(by_channel[name])
        elif name in by_label:
            idx.append(by_label[name])
    return idx or None


def _persist_run(session_id, job_id, params, engine_name, before_emd, after_emd,
                 summary, umap_before, umap_after, injected, corrected_dir):
    rid = str(uuid.uuid4())
    db = SessionLocal()
    try:
        run = BatchCorrectionRun(
            id=rid,
            session_id=session_id,
            job_id=job_id,
            params=_jsonable(params),
            engine=engine_name,
            emd_before=_jsonable(before_emd),
            emd_after=_jsonable(after_emd),
            mean_emd_before=float(summary.get("mean_before", 0.0)),
            mean_emd_after=float(summary.get("mean_after", 0.0)),
            reduction_pct=float(summary.get("reduction_pct", 0.0)),
            umap_before=_jsonable(umap_before),
            umap_after=_jsonable(umap_after),
            injected=_jsonable(injected),
            corrected_dir=str(corrected_dir),
            status="completed",
            created_at=_now(),
        )
        db.add(run)
        db.commit()
        return rid
    finally:
        db.close()


# --------------------------------------------------------------------------- batch correction
def submit_batch_correction(job_id, session_id, params):
    executor.submit(_run_batch_correction, job_id, session_id, params)


def _run_batch_correction(job_id, session_id, params):
    try:
        engine_name = str(params.get("engine", "cytonorm")).lower()
        cofactor = float(params.get("cofactor", 150.0))
        seed = int(params.get("seed", 42))

        # 10 --------------------------------------------------------------- load + transform
        _update(job_id, status="running", progress=10, message="Loading FCS", error=None)
        events, channel_names, marker_labels = io.load_events(
            E1_PATH, transform=True, cofactor=cofactor)
        marker_idx = io.marker_indices(channel_names, exclude_scatter=True)

        # 25 --------------------------------------------------------------- inject synthetic drift
        _update(job_id, progress=25, message="Injecting synthetic drift")
        drift_marker_idx = _resolve_drift_idx(
            params.get("drift_markers") or [], channel_names, marker_labels)
        bd = synth.build_batches(
            events,
            channel_names,
            n_batches=int(params.get("n_batches", 2)),
            drift_marker_idx=drift_marker_idx,
            drift_a=float(params.get("drift_a", 1.3)),
            drift_b=float(params.get("drift_b", 0.2)),
            seed=seed,
        )

        jobdir = os.path.join(str(JOBS_DIR), job_id)
        indir = os.path.join(jobdir, "input")
        os.makedirs(indir, exist_ok=True)

        jobparams = synth.write_job_inputs(bd, indir)
        jobparams["nClus"] = int(params.get("nClus", 10))
        jobparams["nQ"] = int(params.get("nQ", 101))
        jobparams["seed"] = seed
        with open(os.path.join(indir, "params.json"), "w") as fh:
            json.dump(_jsonable(jobparams), fh)

        # 55 --------------------------------------------------------------- correct
        _update(job_id, progress=55, message="Correcting (CytoNorm/ComBat)")
        labels = sorted(bd.batches.keys())
        if engine_name in ("pycombat", "combat"):
            corrected = cytonorm.run_pycombat(bd, marker_idx)
            corrected_dir = os.path.join(jobdir, "output")
            os.makedirs(corrected_dir, exist_ok=True)
            for label, ev in corrected.items():
                io.write_fcs(np.asarray(ev), channel_names,
                             os.path.join(corrected_dir, f"corrected_{label}.fcs"))
        else:
            output_dir = cytonorm.run_cytonorm(jobdir)
            corrected = {}
            for sfile, slabel in zip(jobparams["sample_files"], jobparams["sample_labels"]):
                norm_path = os.path.join(output_dir, "Norm_" + os.path.basename(sfile))
                ev, _cn, _ml = io.load_events(norm_path, transform=False)
                corrected[slabel] = ev
            corrected_dir = output_dir

        # 75 --------------------------------------------------------------- EMD
        _update(job_id, progress=75, message="Computing EMD")
        a_label, b_label = labels[0], labels[1]
        before_emd = emd.emd_between(bd.batches[a_label], bd.batches[b_label],
                                     channel_names, marker_idx)
        after_emd = emd.emd_between(corrected[a_label], corrected[b_label],
                                    channel_names, marker_idx)
        summary = emd.summarize_emd(before_emd, after_emd)

        # 90 --------------------------------------------------------------- UMAP
        _update(job_id, progress=90, message="UMAP embedding")
        umap_before = embed.umap_embed(bd.batches, marker_idx, subsample=30000, seed=seed)
        umap_after = embed.umap_embed(corrected, marker_idx, subsample=30000, seed=seed)

        # 100 -------------------------------------------------------------- persist + done
        rid = _persist_run(session_id, job_id, params, engine_name, before_emd, after_emd,
                           summary, umap_before, umap_after, bd.injected, corrected_dir)
        _update(
            job_id,
            status="completed",
            progress=100,
            message="Done",
            result={"batch_correction_run_id": rid,
                    "reduction_pct": float(summary.get("reduction_pct", 0.0))},
        )
    except Exception as exc:  # noqa: BLE001 - report every failure to the Job row
        _update(job_id, status="failed", message="Failed", error=str(exc))


# --------------------------------------------------------------------------- export
def submit_export(job_id, session_id, run_id):
    executor.submit(_run_export, job_id, session_id, run_id)


def _run_export(job_id, session_id, run_id):
    try:
        _update(job_id, status="running", progress=15, message="Collecting artifacts", error=None)

        db = SessionLocal()
        try:
            run = db.get(BatchCorrectionRun, run_id) if run_id else None
            if run is None:
                run = (
                    db.query(BatchCorrectionRun)
                    .filter(BatchCorrectionRun.session_id == session_id)
                    .order_by(BatchCorrectionRun.created_at.desc())
                    .first()
                )
            if run is None:
                raise RuntimeError("no batch-correction run available to export")
            corrected_dir = run.corrected_dir
            emd_before = run.emd_before or {}
            emd_after = run.emd_after or {}
            injected = run.injected or {}
        finally:
            db.close()

        os.makedirs(str(EXPORTS_DIR), exist_ok=True)
        zip_path = os.path.join(str(EXPORTS_DIR), f"{job_id}.zip")

        _update(job_id, progress=60, message="Writing zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if corrected_dir and os.path.isdir(corrected_dir):
                for path in sorted(Path(corrected_dir).glob("*.fcs")):
                    zf.write(str(path), arcname=os.path.join("corrected_fcs", path.name))

            lines = ["marker,emd_before,emd_after"]
            for marker in emd_before:
                lines.append(f"{marker},{emd_before.get(marker, '')},{emd_after.get(marker, '')}")
            zf.writestr("emd.csv", "\n".join(lines) + "\n")

            zf.writestr("injected.json", json.dumps(_jsonable(injected), indent=2))
            zf.writestr("SYNTHETIC_WARNING.txt", SYNTHETIC_WARNING)

        _update(
            job_id,
            status="completed",
            progress=100,
            message="Done",
            result={"path": zip_path, "export_id": job_id},
        )
    except Exception as exc:  # noqa: BLE001
        _update(job_id, status="failed", message="Failed", error=str(exc))
