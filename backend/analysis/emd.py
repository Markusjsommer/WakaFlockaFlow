"""Earth-Mover-Distance (1D Wasserstein) per marker between two batches."""
import numpy as np
from scipy.stats import wasserstein_distance


def emd_between(a: np.ndarray, b: np.ndarray, channel_names, marker_idx: list) -> dict:
    """Per-marker Wasserstein distance between batch ``a`` and batch ``b``.

    Returns {marker_name: distance} over the columns in ``marker_idx``.
    """
    a = np.asarray(a)
    b = np.asarray(b)
    out = {}
    for i in marker_idx:
        m = channel_names[i]
        out[m] = float(wasserstein_distance(a[:, i], b[:, i]))
    return out


def summarize_emd(before: dict, after: dict) -> dict:
    """Aggregate before/after per-marker EMD into means + reduction percent."""
    markers = list(before.keys())

    per_marker = {}
    for m in markers:
        per_marker[m] = {
            "before": float(before[m]),
            "after": float(after.get(m, float("nan"))),
        }

    mean_before = float(np.mean([before[m] for m in markers])) if markers else 0.0
    after_vals = [after[m] for m in markers if m in after]
    mean_after = float(np.mean(after_vals)) if after_vals else 0.0

    reduction_pct = 0.0
    if mean_before > 0:
        reduction_pct = float((mean_before - mean_after) / mean_before * 100.0)

    return {
        "mean_before": mean_before,
        "mean_after": mean_after,
        "reduction_pct": reduction_pct,
        "per_marker": per_marker,
    }
