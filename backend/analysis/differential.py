"""Differential abundance (DA) + differential state (DS) testing for a cohort.

Two engines behind one interface:

  * diffcyt (R): edgeR (DA) + limma (DS), the field-standard method. Run via the
    shared Rscript file-IPC (run_diffcyt.R). Preferred when installed.
  * python: a dependency-light fallback (scipy rank tests + Benjamini-Hochberg)
    so differential testing works everywhere, including before the R packages
    are built into the image.

Both return the same shape:
    {"engine": str,
     "da": [{"metacluster_id","log_fc","p_value","p_adj","log_cpm"}],
     "ds": [{"metacluster_id","marker","log_fc","p_value","p_adj"}],
     "notes": {...}}
"""
from __future__ import annotations

import csv
import json
import os
import tempfile

import numpy as np

_EPS = 1e-6


# --------------------------------------------------------------------------- helpers
def _bh_adjust(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR. NaN p-values pass through as NaN."""
    idx = [i for i, p in enumerate(pvals) if p is not None and not np.isnan(p)]
    m = len(idx)
    adj = [float("nan")] * len(pvals)
    if m == 0:
        return adj
    order = sorted(idx, key=lambda i: pvals[i])
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        k = m - rank + 1  # BH rank (largest first)
        val = pvals[i] * m / k
        prev = min(prev, val)
        adj[i] = min(1.0, prev)
    return adj


def _groups_from(samples: list[dict], field: str, contrast: list | None):
    """Map group label -> [sample_index]. Restrict to ``contrast`` levels if given."""
    def value(s):
        if field == "group":
            return s.get("group")
        if field == "batch":
            return s.get("batch")
        return (s.get("covariates") or {}).get(field)

    groups: dict[str, list[int]] = {}
    for s in samples:
        g = value(s)
        if g is None or str(g).strip() == "":
            continue
        groups.setdefault(str(g), []).append(int(s["sample_index"]))

    if contrast:
        groups = {g: groups.get(g, []) for g in contrast if g in groups}
    return groups


def _test(value_lists: list[list[float]]):
    """Rank test across groups: Mann-Whitney (2) / Kruskal-Wallis (3+). -> p or NaN."""
    from scipy import stats

    lists = [np.asarray(v, dtype=float) for v in value_lists]
    lists = [v[~np.isnan(v)] for v in lists]
    if any(len(v) < 1 for v in lists) or len(lists) < 2:
        return float("nan")
    try:
        if len(lists) == 2:
            if len(lists[0]) < 1 or len(lists[1]) < 1:
                return float("nan")
            _u, p = stats.mannwhitneyu(lists[0], lists[1], alternative="two-sided")
        else:
            _h, p = stats.kruskal(*lists)
        return float(p)
    except ValueError:
        return float("nan")


# --------------------------------------------------------------------------- python engine
def run_python_fallback(matrices: dict, params: dict) -> dict:
    field = params.get("group_field", "group")
    contrast = params.get("contrast")
    min_samples = int(params.get("min_samples", 1))

    groups = _groups_from(matrices["samples"], field, contrast)
    labels = list(groups.keys())
    if len(labels) < 2:
        raise RuntimeError(
            "differential testing needs at least two groups; tag samples with a group first"
        )
    ordered = contrast if contrast else labels
    ordered = [g for g in ordered if g in groups]

    totals = matrices["totals"]
    counts = matrices["counts"]
    medians = matrices["medians"]
    mc_ids = matrices["metacluster_ids"]
    markers = matrices["markers"]

    small = [g for g in ordered if len(groups[g]) < 2]
    notes = {}
    if small:
        notes["low_replication"] = (
            f"groups with <2 samples (rank tests underpowered): {', '.join(small)}"
        )

    # ---- differential abundance ----
    def prop(mc, si):
        tot = totals.get(si, 0) or 1
        return counts.get(mc, {}).get(si, 0) / tot

    da_rows = []
    da_p = []
    for mc in mc_ids:
        per_group = [[prop(mc, si) for si in groups[g]] for g in ordered]
        means = [float(np.mean(v)) if v else float("nan") for v in per_group]
        if len(ordered) == 2:
            log_fc = float(np.log2((means[1] + _EPS) / (means[0] + _EPS)))
        else:
            mx, mn = np.nanmax(means), np.nanmin(means)
            log_fc = float(np.log2((mx + _EPS) / (mn + _EPS)))
        all_props = [prop(mc, si) for g in ordered for si in groups[g]]
        log_cpm = float(np.log2(np.mean(all_props) * 1e6 + 1)) if all_props else float("nan")
        p = _test(per_group)
        da_p.append(p)
        da_rows.append({"metacluster_id": int(mc), "log_fc": log_fc,
                        "p_value": p, "p_adj": None, "log_cpm": log_cpm})
    for row, padj in zip(da_rows, _bh_adjust(da_p)):
        row["p_adj"] = None if np.isnan(padj) else float(padj)

    # ---- differential state ----
    ds_rows = []
    ds_p = []
    for mc in mc_ids:
        mc_med = medians.get(mc, {})
        for marker in markers:
            per_group = [
                [mc_med.get(si, {}).get(marker) for si in groups[g]
                 if mc_med.get(si, {}).get(marker) is not None]
                for g in ordered
            ]
            means = [float(np.mean(v)) if v else float("nan") for v in per_group]
            if len(ordered) == 2:
                log_fc = float(means[1] - means[0])  # arcsinh-space difference
            else:
                log_fc = float(np.nanmax(means) - np.nanmin(means))
            p = _test(per_group)
            ds_p.append(p)
            ds_rows.append({"metacluster_id": int(mc), "marker": marker,
                            "log_fc": log_fc, "p_value": p, "p_adj": None})
    for row, padj in zip(ds_rows, _bh_adjust(ds_p)):
        row["p_adj"] = None if np.isnan(padj) else float(padj)

    return {"engine": "python", "da": da_rows, "ds": ds_rows, "notes": notes}


# --------------------------------------------------------------------------- diffcyt (R)
def setup_diff_job(jobdir: str, matrices: dict, params: dict) -> None:
    """Stage the diffcyt inputs under ``jobdir/input``."""
    indir = os.path.join(jobdir, "input")
    os.makedirs(indir, exist_ok=True)
    os.makedirs(os.path.join(jobdir, "output"), exist_ok=True)

    samples = matrices["samples"]
    mc_ids = matrices["metacluster_ids"]
    markers = matrices["markers"]
    counts = matrices["counts"]
    medians = matrices["medians"]

    # counts.csv: rows = metacluster, columns = sample_index
    with open(os.path.join(indir, "counts.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metacluster_id"] + [str(s["sample_index"]) for s in samples])
        for mc in mc_ids:
            w.writerow([mc] + [counts.get(mc, {}).get(s["sample_index"], 0) for s in samples])

    # sample_info.csv
    with open(os.path.join(indir, "sample_info.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_index", "sample_label", "group", "batch", "n_events_used"])
        for s in samples:
            w.writerow([s["sample_index"], s["sample_label"], s.get("group") or "",
                        s.get("batch") or "", s.get("n_events_used", 0)])

    # medians.csv: long form
    with open(os.path.join(indir, "medians.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metacluster_id", "sample_index", "marker", "value"])
        for mc in mc_ids:
            for si, md in medians.get(mc, {}).items():
                for marker in markers:
                    if marker in md:
                        w.writerow([mc, si, marker, md[marker]])

    with open(os.path.join(indir, "params.json"), "w") as fh:
        json.dump({
            "group_field": params.get("group_field", "group"),
            "contrast": params.get("contrast"),
            "covariates": params.get("covariates") or [],
            "paired_field": params.get("paired_field"),
            "min_cells": int(params.get("min_cells", 0)),
            "min_samples": int(params.get("min_samples", 2)),
        }, fh)


def collect_diff(output_dir: str) -> dict:
    """Read diffcyt outputs (da.csv, ds.csv) written by run_diffcyt.R."""
    def read_rows(name):
        path = os.path.join(output_dir, name)
        if not os.path.exists(path):
            return []
        with open(path) as fh:
            return list(csv.DictReader(fh))

    def num(v):
        try:
            f = float(v)
            return None if np.isnan(f) else f
        except (TypeError, ValueError):
            return None

    da = [{"metacluster_id": int(float(r["metacluster_id"])),
           "log_fc": num(r.get("log_fc")), "p_value": num(r.get("p_value")),
           "p_adj": num(r.get("p_adj")), "log_cpm": num(r.get("log_cpm"))}
          for r in read_rows("da.csv")]
    ds = [{"metacluster_id": int(float(r["metacluster_id"])), "marker": r["marker"],
           "log_fc": num(r.get("log_fc")), "p_value": num(r.get("p_value")),
           "p_adj": num(r.get("p_adj"))}
          for r in read_rows("ds.csv")]
    return {"engine": "diffcyt", "da": da, "ds": ds, "notes": {}}


def run_diffcyt(matrices: dict, params: dict) -> dict:
    """Run the diffcyt R recipe; raises RuntimeError if R/diffcyt is unavailable."""
    from analysis import r_engine

    jobdir = tempfile.mkdtemp(prefix="diffcyt_")
    setup_diff_job(jobdir, matrices, params)
    output_dir = r_engine.run_r_job("run_diffcyt.R", jobdir, timeout=900)
    return collect_diff(output_dir)


def run_differential(matrices: dict, params: dict) -> dict:
    """Dispatch to the requested engine.

    engine: 'python' (default, always available) | 'diffcyt' (R) | 'auto'
    (try diffcyt, fall back to python on any R error).
    """
    engine = (params.get("engine") or "python").lower()
    if engine == "python":
        return run_python_fallback(matrices, params)
    if engine == "diffcyt":
        return run_diffcyt(matrices, params)
    # auto
    try:
        return run_diffcyt(matrices, params)
    except Exception as exc:  # noqa: BLE001
        result = run_python_fallback(matrices, params)
        result.setdefault("notes", {})["diffcyt_fallback"] = (
            f"diffcyt unavailable ({exc}); used the Python rank-test fallback"
        )
        return result
