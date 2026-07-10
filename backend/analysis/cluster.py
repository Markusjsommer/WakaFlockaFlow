"""Automated population identification: FlowSOM clustering + UMAP embedding.

This is the analytical core of the population-ID workflow. ``run_flowsom`` groups
cells into metaclusters (candidate populations) using the verified Python ``flowsom``
0.2.2 engine; ``umap_coords`` produces a 2D embedding of a subsample of cells for
visualization.

Heavy engine imports (anndata, flowsom, umap) are done lazily inside the functions so
this module - and the API router that imports it - always loads even before those
optional dependencies are installed.
"""
from __future__ import annotations

import numpy as np


def run_flowsom(events, channel_names, marker_idx,
                xdim: int = 10, ydim: int = 10, n_clusters: int = 10,
                seed: int = 42) -> dict:
    """Cluster cells into metaclusters with FlowSOM.

    Args:
        events:        float32 ndarray (n_events, n_channels), already transformed.
        channel_names: list[str] of $PnN channel names, one per column of ``events``.
        marker_idx:    list[int] column indices to cluster on (fluorophore markers).
        xdim, ydim:    SOM grid dimensions.
        n_clusters:    number of metaclusters (final populations).
        seed:          RNG seed for reproducibility.

    Returns:
        {
          "labels": np.ndarray[int] of length n_events (metacluster per input cell),
          "populations": [
             {"metacluster_id": int, "cell_count": int, "percentage": float (0-100),
              "median_expression": {marker_name: float, ...}},
             ...  sorted by metacluster_id
          ]
        }
    """
    import anndata as ad
    import flowsom as flowsom_mod

    events = np.asarray(events, dtype=np.float32)
    marker_idx = list(marker_idx)
    marker_names = [channel_names[i] for i in marker_idx]

    n_events = int(events.shape[0])

    # Build the AnnData input on the selected marker columns only.
    adata = ad.AnnData(X=events[:, marker_idx].astype("float32"))
    adata.var_names = list(marker_names)

    fsom = flowsom_mod.FlowSOM(
        adata,
        cols_to_use=list(adata.var_names),
        xdim=int(xdim),
        ydim=int(ydim),
        n_clusters=int(n_clusters),
        seed=int(seed),
    )

    obs = fsom.get_cell_data().obs
    labels = np.asarray(obs["metaclustering"]).astype(int)

    # Per-population summary tables, computed on the transformed marker matrix.
    marker_matrix = events[:, marker_idx]
    populations = []
    for mc in sorted(np.unique(labels).tolist()):
        mask = labels == mc
        count = int(mask.sum())
        sub = marker_matrix[mask]
        if sub.shape[0] > 0:
            medians = np.median(sub, axis=0)
        else:
            medians = np.zeros(len(marker_idx), dtype=np.float32)
        median_expression = {
            name: float(medians[j]) for j, name in enumerate(marker_names)
        }
        populations.append(
            {
                "metacluster_id": int(mc),
                "cell_count": count,
                "percentage": float(100.0 * count / n_events) if n_events else 0.0,
                "median_expression": median_expression,
            }
        )

    return {"labels": labels, "populations": populations}


def umap_coords(events, marker_idx, subsample: int = 30000, seed: int = 42,
                preselected_idx=None):
    """2D UMAP embedding of a subsample of cells.

    Subsamples up to ``subsample`` cell indices, fits a 2D UMAP on the selected
    marker columns, and returns the sampled indices alongside their coordinates.

    When ``preselected_idx`` is given the internal random subsampling is skipped
    and exactly those rows are embedded (used by cohort mode, which chooses a
    stratified per-sample subset upstream so labels stay aligned).

    Returns:
        idx: np.ndarray[int]   sampled (and sorted) cell indices into ``events``
        xy:  np.ndarray[m, 2]  2D coordinates for those cells (float32)
    """
    import umap

    events = np.asarray(events, dtype=np.float32)
    marker_idx = list(marker_idx)

    if preselected_idx is not None:
        idx = np.asarray(preselected_idx, dtype=int)
    else:
        n = int(events.shape[0])
        rng = np.random.default_rng(seed)
        if n > subsample:
            idx = np.sort(rng.choice(n, size=subsample, replace=False))
        else:
            idx = np.arange(n)

    X = events[idx][:, marker_idx].astype(np.float32)
    reducer = umap.UMAP(n_components=2, random_state=seed)
    emb = reducer.fit_transform(X)

    return idx, np.asarray(emb, dtype=np.float32)
