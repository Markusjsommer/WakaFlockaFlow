"""Unified R invocation for the spectral / normalization R jobs.

Works in BOTH deployment shapes with one entrypoint:

  * dev            -> R lives in a per-recipe Docker image (WAKAFLAKA_R_MODE=docker)
  * combined image -> R is on PATH next to the API (WAKAFLAKA_R_MODE=local)

All R recipes share the same file-based IPC contract as run_cytonorm.R / run_unmix.R:
    <jobdir>/input/...      - inputs staged by the caller
    <jobdir>/output/*.fcs   - results
    <jobdir>/output/done.json | <jobdir>/error.json - completion markers

``run_r_job`` runs the script, then reads those markers: an error.json surfaces the
R-side ``error_message`` as a RuntimeError; a missing done.json surfaces the process
stderr tail. On success it returns the ``output/`` directory path.
"""
import os
import shutil
import subprocess
import json

# 'docker' (dev, per-recipe image) or 'local' (inside the packaged combined image).
R_MODE = os.environ.get("WAKAFLAKA_R_MODE", "docker")

# Directory holding the validated R recipes (backend/r_scripts by default).
R_SCRIPTS_DIR = os.environ.get(
    "WAKAFLAKA_R_SCRIPTS",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "r_scripts")),
)

# Docker image per recipe (dev mode only).
IMAGE_FOR = {
    "run_unmix.R": "wakaflaka-r:unmix",
    "run_cytonorm.R": "wakaflaka-r:cytonorm",
}


def _read_error_message(error_path: str) -> str:
    try:
        with open(error_path) as fh:
            err = json.load(fh)
        return str(err.get("error_message", "R job failed"))
    except Exception:  # noqa: BLE001
        return "R job failed"


def _stderr_tail(completed, limit: int = 2000) -> str:
    stderr = getattr(completed, "stderr", "") or ""
    stdout = getattr(completed, "stdout", "") or ""
    tail = (stderr or stdout).strip()
    if not tail:
        return "R job produced no output/done.json and no stderr"
    return tail[-limit:]


def run_r_job(script: str, jobdir: str, timeout: int = 1800) -> str:
    """Run an R recipe against ``jobdir`` and return the output/ directory path.

    ``jobdir`` must already contain the staged ``input/`` tree. Raises RuntimeError
    when the recipe reports an error.json, or when it exits without writing
    output/done.json (with the process stderr tail as the message).
    """
    jobdir = os.path.abspath(jobdir)
    output_dir = os.path.join(jobdir, "output")
    done_path = os.path.join(output_dir, "done.json")
    error_path = os.path.join(jobdir, "error.json")

    # Clear any stale completion markers before launching.
    for p in (done_path, error_path):
        if os.path.exists(p):
            os.remove(p)

    if R_MODE == "local":
        cmd = ["Rscript", os.path.join(R_SCRIPTS_DIR, script), jobdir]
    else:
        # Docker: the R process sees the job tree at /job, so the script must live
        # inside the mounted jobdir.
        shutil.copyfile(os.path.join(R_SCRIPTS_DIR, script), os.path.join(jobdir, script))
        image = IMAGE_FOR.get(script)
        if image is None:
            raise RuntimeError(f"no docker image mapped for R script {script!r}")
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{jobdir}:/job",
            image,
            "Rscript", f"/job/{script}", "/job",
        ]

    try:
        completed = subprocess.run(
            cmd, check=False, timeout=timeout,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"R job {script} timed out after {timeout}s")

    if os.path.exists(error_path):
        raise RuntimeError(_read_error_message(error_path))
    if not os.path.exists(done_path):
        raise RuntimeError(_stderr_tail(completed))

    return output_dir
