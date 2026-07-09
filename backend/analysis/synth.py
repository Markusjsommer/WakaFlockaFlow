"""Synthetic batch-effect injection.

The single real acquisition is randomly split into pseudo-batches 'A', 'B', ...
Batch 'A' is the identity reference; every later batch receives a known monotone
drift  x' = drift_a * x + drift_b  on the selected marker columns, applied to
BOTH that batch's samples and its copy of the shared control aliquot.
"""
import os
from dataclasses import dataclass

import numpy as np

from . import io


@dataclass
class BatchData:
    channels: list
    batches: dict            # label -> float32 ndarray (n_events, n_channels)
    controls: dict           # label -> float32 ndarray (control_size, n_channels)
    injected: dict           # marker_name -> {"a", "b", "batch"}


def build_batches(events, channels, n_batches: int = 2,
                  drift_marker_idx=None, drift_a: float = 1.3,
                  drift_b: float = 0.2, control_size: int = 20000,
                  seed: int = 42) -> BatchData:
    """Split ``events`` into ``n_batches`` pseudo-batches and inject drift.

    A single shared control aliquot of ``control_size`` events is drawn and
    copied into every batch. Batch 0 ('A') is the untouched reference; batches
    i >= 1 get x' = drift_a*x + drift_b on ``drift_marker_idx`` columns of both
    their samples and their control copy.
    """
    events = np.asarray(events, dtype=np.float32)
    channels = list(channels)
    rng = np.random.default_rng(seed)
    n = events.shape[0]

    if drift_marker_idx is None:
        drift_marker_idx = io.marker_indices(channels)
    drift_marker_idx = list(drift_marker_idx)

    labels = [chr(ord("A") + i) for i in range(n_batches)]

    # random split of all events into n_batches
    perm = rng.permutation(n)
    splits = np.array_split(perm, n_batches)

    # single shared control aliquot copied into every batch
    csize = min(control_size, n)
    control_idx = rng.choice(n, size=csize, replace=False)
    shared_control = events[control_idx].astype(np.float32).copy()

    batches = {}
    controls = {}
    injected = {}

    for i, label in enumerate(labels):
        samp = events[splits[i]].astype(np.float32).copy()
        ctrl = shared_control.copy()

        if i >= 1:
            for c in drift_marker_idx:
                samp[:, c] = drift_a * samp[:, c] + drift_b
                ctrl[:, c] = drift_a * ctrl[:, c] + drift_b
                injected[channels[c]] = {
                    "a": float(drift_a),
                    "b": float(drift_b),
                    "batch": label,
                }

        batches[label] = samp
        controls[label] = ctrl

    return BatchData(channels=channels, batches=batches,
                     controls=controls, injected=injected)


def write_job_inputs(bd: BatchData, indir: str) -> dict:
    """Write control_<label>.fcs and sample_<label>.fcs for every batch.

    Returns a params dict (nClus / nQ / seed to be filled in by the caller).
    """
    os.makedirs(indir, exist_ok=True)

    marker_idx = io.marker_indices(bd.channels)
    marker_channel_names = [bd.channels[i] for i in marker_idx]

    control_files = []
    control_labels = []
    sample_files = []
    sample_labels = []

    for label in bd.batches:
        cfile = os.path.join(indir, f"control_{label}.fcs")
        sfile = os.path.join(indir, f"sample_{label}.fcs")
        io.write_fcs(bd.controls[label], bd.channels, cfile)
        io.write_fcs(bd.batches[label], bd.channels, sfile)
        # R (run_cytonorm.R) resolves these via file.path(indir, ...), so store
        # basenames relative to the mounted /job/input, not host-absolute paths.
        control_files.append(os.path.basename(cfile))
        control_labels.append(label)
        sample_files.append(os.path.basename(sfile))
        sample_labels.append(label)

    return {
        "channels": marker_channel_names,
        "control_files": control_files,
        "control_labels": control_labels,
        "sample_files": sample_files,
        "sample_labels": sample_labels,
    }
