"""Batch-correction engines.

run_cytonorm  - runs the R CytoNorm pipeline inside Docker (primary engine).
run_pycombat  - pure-python pyComBat fallback.
"""
import os
import json
import time
import shutil
import subprocess

import numpy as np
import pandas as pd
from combat.pycombat import pycombat

R_SCRIPT_SRC = "/Users/markus/_work/caveman_flow/backend/r_scripts/run_cytonorm.R"


def run_cytonorm(jobdir: str, image: str = "wakaflaka-r:cytonorm",
                 timeout: int = 1800) -> str:
    """Run CytoNorm in Docker against ``jobdir`` and return the output dir.

    Copies run_cytonorm.R into ``jobdir``, launches
        docker run --rm -v <ABS jobdir>:/job <image> Rscript /job/run_cytonorm.R /job
    then polls <jobdir>/output/done.json (success) / <jobdir>/error.json
    (raises RuntimeError with the reported error_message).
    Returns <jobdir>/output (which holds the Norm_*.fcs files).
    """
    jobdir = os.path.abspath(jobdir)
    os.makedirs(jobdir, exist_ok=True)

    dst_script = os.path.join(jobdir, "run_cytonorm.R")
    shutil.copyfile(R_SCRIPT_SRC, dst_script)

    output_dir = os.path.join(jobdir, "output")
    done_path = os.path.join(output_dir, "done.json")
    error_path = os.path.join(jobdir, "error.json")

    # clear any stale completion markers from a previous run
    for p in (done_path, error_path):
        if os.path.exists(p):
            os.remove(p)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{jobdir}:/job",
        image,
        "Rscript", "/job/run_cytonorm.R", "/job",
    ]

    start = time.time()
    try:
        subprocess.run(cmd, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("CytoNorm docker run timed out")

    # poll for the completion / error markers
    while time.time() - start < timeout:
        if os.path.exists(error_path):
            raise RuntimeError(_read_error(error_path))
        if os.path.exists(done_path):
            return output_dir
        time.sleep(2)

    # final check after the polling window
    if os.path.exists(error_path):
        raise RuntimeError(_read_error(error_path))
    if os.path.exists(done_path):
        return output_dir

    raise RuntimeError("CytoNorm timed out waiting for output/done.json")


def _read_error(error_path: str) -> str:
    try:
        with open(error_path) as f:
            err = json.load(f)
        return str(err.get("error_message", "CytoNorm failed"))
    except Exception:
        return "CytoNorm failed"


def run_pycombat(bd, marker_idx: list) -> dict:
    """Pure-python ComBat fallback.

    Pools all batches' sample events, builds a batch-label vector, and applies
    ComBat to the marker columns. Returns corrected full events per batch,
    preserving shapes and column order (only marker columns are modified).
    """
    marker_idx = list(marker_idx)
    labels = list(bd.batches.keys())

    mats = []
    sizes = []
    batch_vector = []
    for label in labels:
        ev = np.asarray(bd.batches[label], dtype=np.float32)
        mats.append(ev)
        sizes.append(ev.shape[0])
        batch_vector.extend([label] * ev.shape[0])

    pooled = np.vstack(mats)  # (N, C)

    # combat expects a features x samples DataFrame
    marker_names = [bd.channels[i] for i in marker_idx]
    df = pd.DataFrame(
        pooled[:, marker_idx].T,
        index=marker_names,
        columns=[f"s{i}" for i in range(pooled.shape[0])],
    )

    corrected = pycombat(df, batch_vector)
    corrected_arr = np.asarray(corrected).T  # (N, n_markers)

    out = {}
    start = 0
    for label, sz in zip(labels, sizes):
        block = pooled[start:start + sz].copy()
        block[:, marker_idx] = corrected_arr[start:start + sz]
        out[label] = block.astype(np.float32)
        start += sz

    return out
