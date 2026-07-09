"""Staging + collection helpers for the AutoSpectral unmix R job.

The R recipe (backend/r_scripts/run_unmix.R) reads a fixed input tree and writes a
single per-marker FCS into output/. These helpers translate a resolved raw file +
control list + UI params into that tree, and pick the unmixed sample back out.
"""
import os
import glob
import json
import shutil


def setup_unmix_job(indir: str, raw_path: str, control_paths: list, params: dict) -> None:
    """Stage the run_unmix.R input tree under ``indir``.

    Writes:
        <indir>/raw.fcs                - the raw detector sample
        <indir>/controls/<basename>    - each single-stain / unstained control
        <indir>/params.json            - {cytometer, af_control, bead_negative}
    """
    params = params or {}
    indir = os.path.abspath(indir)
    ctrldir = os.path.join(indir, "controls")
    os.makedirs(ctrldir, exist_ok=True)

    shutil.copyfile(raw_path, os.path.join(indir, "raw.fcs"))

    for src in control_paths:
        shutil.copyfile(src, os.path.join(ctrldir, os.path.basename(src)))

    payload = {
        "cytometer": params.get("cytometer", "aurora"),
        "af_control": params.get("af_control", "PBMC_unstained.fcs"),
        "bead_negative": params.get("bead_negative", "Beads_unstained.fcs"),
    }
    with open(os.path.join(indir, "params.json"), "w") as fh:
        json.dump(payload, fh)


def collect_unmixed(outdir: str) -> str:
    """Return the path to the single unmixed *.fcs written into ``outdir``."""
    matches = sorted(glob.glob(os.path.join(outdir, "*.fcs")))
    if not matches:
        raise RuntimeError(f"no unmixed .fcs found in {outdir}")
    return matches[0]
