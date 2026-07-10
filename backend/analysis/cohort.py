"""Cohort pooling for multi-sample joint clustering.

Biologists routinely have tens to hundreds of samples and want them on ONE
shared UMAP so populations are directly comparable. This module concatenates
several FCS files' event matrices onto a shared marker set, capping cells per
sample so memory stays bounded, and keeps a per-cell sample label throughout so
the frontend can highlight one sample on the shared embedding and so populations
can be quantified per sample (the input to differential testing).

Samples may use different panels: clustering runs on the INTERSECTION of markers
(matched by a loose name key), and markers absent from any selected sample are
reported as dropped.

Everything downstream (FlowSOM, UMAP, annotation) is reused unchanged: the pooled
matrix is passed as ``events`` with the shared marker labels as ``channel_names``
and every column selected as a clustering marker.
"""
from __future__ import annotations

import re

import numpy as np

from analysis import io as analysis_io

# Cell caps. Per-sample caps keep any one large file from dominating; total caps
# bound memory and UMAP runtime. FlowSOM trains on the pooled matrix (<=2M x M
# floats ~ a few hundred MB); UMAP is superlinear so its subset is capped hard.
CAP_FLOWSOM_PER_SAMPLE = 50_000
CAP_FLOWSOM_TOTAL = 2_000_000
CAP_UMAP_PER_SAMPLE = 5_000
CAP_UMAP_TOTAL = 200_000


def _marker_key(label: str) -> str:
    """Loose canonical key for matching the SAME marker across files.

    Not the annotation token (that collapses fluorophores to ''); this only needs
    a stable identity per marker. Strips a trailing area suffix (-A/-H/-W) and all
    punctuation, uppercases. 'CD3-A' -> 'CD3', 'Ki-67' -> 'KI67', 'PD-1' -> 'PD1'.
    """
    s = str(label or "").strip()
    s = re.sub(r"[-_ ]?[AHW]$", "", s)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def resolve_shared_markers(samples: list[dict], markers: list[str] | None = None):
    """Intersect the clustering markers across ``samples`` by name key.

    Args:
        samples: ordered list of {"file_id", "path", "sample_label"} dicts.
        markers: optional explicit marker label/name allow-list to restrict to.

    Returns:
        shared_keys:   list[str] marker keys common to every sample (sorted).
        shared_labels: list[str] display label per shared key (from the 1st sample).
        per_file:      {file_id: {key: column_index}} for aligning each sample.
        dropped:       {sample_label: [labels present in that sample but not shared]}.
    """
    want = {_marker_key(m) for m in markers} if markers else None

    per_file: dict[str, dict[str, int]] = {}
    label_for_key: dict[str, str] = {}
    file_keys: list[set] = []
    file_all_labels: dict[str, dict[str, str]] = {}  # file_id -> {key: label}

    for s in samples:
        _events, channel_names, marker_labels = analysis_io.load_events(
            s["path"], transform=False
        )
        idx = analysis_io.marker_indices(channel_names, exclude_scatter=True)
        keymap: dict[str, int] = {}
        labelmap: dict[str, str] = {}
        for i in idx:
            label = marker_labels[i] if i < len(marker_labels) else channel_names[i]
            key = _marker_key(label)
            if not key:
                continue
            if want is not None and key not in want:
                continue
            keymap.setdefault(key, i)
            labelmap.setdefault(key, label)
            label_for_key.setdefault(key, label)  # first sample wins for display
        per_file[s["file_id"]] = keymap
        file_all_labels[s["file_id"]] = labelmap
        file_keys.append(set(keymap))

    if not file_keys:
        return [], [], {}, {}

    shared = set.intersection(*file_keys) if len(file_keys) > 1 else file_keys[0]
    shared_keys = sorted(shared)
    shared_labels = [label_for_key[k] for k in shared_keys]

    dropped: dict[str, list[str]] = {}
    for s in samples:
        labels_here = file_all_labels[s["file_id"]]
        extra = [labels_here[k] for k in labels_here if k not in shared]
        if extra:
            dropped[s["sample_label"]] = sorted(extra)

    return shared_keys, shared_labels, per_file, dropped


def _per_sample_cap(n_samples: int) -> int:
    """Per-sample FlowSOM cap that also respects the pooled total cap."""
    if n_samples <= 0:
        return CAP_FLOWSOM_PER_SAMPLE
    return max(1, min(CAP_FLOWSOM_PER_SAMPLE, CAP_FLOWSOM_TOTAL // n_samples))


def build_pool(samples: list[dict], shared_keys: list[str], per_file: dict,
               seed: int = 42, cofactor: float = 150.0):
    """Load, align, cap and concatenate samples into one pooled marker matrix.

    Loads one sample at a time (never holding every raw matrix at once). Each
    sample's events are arcsinh-transformed, reduced to the shared marker columns
    in ``shared_keys`` order, then randomly capped.

    Returns a dict:
        pooled_X:     float32 (N_pooled, M) transformed shared-marker matrix
        sample_idx:   int (N_pooled,)  sample_index per pooled cell
        umap_idx:     int (K,)  indices into pooled_X for the UMAP subset (stratified)
        per_sample:   list of {"sample_index","n_events","n_events_used"}
    """
    n_samples = len(samples)
    cap = _per_sample_cap(n_samples)
    M = len(shared_keys)

    blocks: list[np.ndarray] = []
    sample_codes: list[np.ndarray] = []
    umap_offsets: list[np.ndarray] = []  # umap indices into the final pooled array
    per_sample: list[dict] = []
    running = 0

    for s in samples:
        si = int(s["sample_index"])
        events, channel_names, _labels = analysis_io.load_events(
            s["path"], transform=True, cofactor=cofactor
        )
        n_full = int(events.shape[0])
        colmap = per_file.get(s["file_id"], {})
        cols = [colmap[k] for k in shared_keys]
        Xi = np.asarray(events[:, cols], dtype=np.float32) if cols else \
            np.zeros((n_full, M), dtype=np.float32)

        rng = np.random.default_rng(int(seed) + si)
        if n_full > cap:
            keep = np.sort(rng.choice(n_full, size=cap, replace=False))
        else:
            keep = np.arange(n_full)
        Xi = Xi[keep]
        used = int(Xi.shape[0])

        # Stratified UMAP subset: cap per sample.
        u_cap = min(CAP_UMAP_PER_SAMPLE, used)
        if used > u_cap:
            u_local = np.sort(rng.choice(used, size=u_cap, replace=False))
        else:
            u_local = np.arange(used)
        umap_offsets.append(u_local + running)

        blocks.append(Xi)
        sample_codes.append(np.full(used, si, dtype=np.int32))
        per_sample.append(
            {"sample_index": si, "n_events": n_full, "n_events_used": used}
        )
        running += used

    if blocks:
        pooled_X = np.vstack(blocks)
        sample_idx = np.concatenate(sample_codes)
        umap_idx = np.concatenate(umap_offsets) if umap_offsets else np.arange(0)
    else:
        pooled_X = np.zeros((0, M), dtype=np.float32)
        sample_idx = np.zeros(0, dtype=np.int32)
        umap_idx = np.zeros(0, dtype=int)

    # Enforce the global UMAP cap (stratified subset may still exceed it).
    if umap_idx.shape[0] > CAP_UMAP_TOTAL:
        rng = np.random.default_rng(int(seed))
        umap_idx = np.sort(rng.choice(umap_idx, size=CAP_UMAP_TOTAL, replace=False))

    return {
        "pooled_X": pooled_X,
        "sample_idx": sample_idx,
        "umap_idx": umap_idx,
        "per_sample": per_sample,
    }


def per_sample_stats(pooled_X, labels, sample_idx, shared_labels,
                     metacluster_ids, n_events_used):
    """population x sample quantification from the pooled clustering result.

    Args:
        pooled_X:       (N, M) transformed pooled matrix.
        labels:         (N,) metacluster per pooled cell.
        sample_idx:     (N,) sample_index per pooled cell.
        shared_labels:  list[str] marker labels for pooled_X columns.
        metacluster_ids:sorted list of metacluster ids.
        n_events_used:  {sample_index: cells contributed} for the % denominator.

    Returns a list of {"sample_index","metacluster_id","cell_count",
    "percentage_of_sample","median_expression"} for every (sample, metacluster).
    """
    labels = np.asarray(labels).astype(int)
    sample_idx = np.asarray(sample_idx).astype(int)
    out: list[dict] = []
    for si in sorted(set(int(x) for x in sample_idx.tolist())):
        smask = sample_idx == si
        denom = int(n_events_used.get(si, int(smask.sum()))) or 1
        Xs = pooled_X[smask]
        ls = labels[smask]
        for mc in metacluster_ids:
            mmask = ls == mc
            count = int(mmask.sum())
            if count > 0:
                med = np.median(Xs[mmask], axis=0)
                medians = {shared_labels[j]: float(med[j])
                           for j in range(len(shared_labels))}
            else:
                medians = {}
            out.append({
                "sample_index": si,
                "metacluster_id": int(mc),
                "cell_count": count,
                "percentage_of_sample": float(100.0 * count / denom),
                "median_expression": medians,
            })
    return out
