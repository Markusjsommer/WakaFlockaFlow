"""UMAP embedding of pooled pseudo-batches for overlap visualization."""
import numpy as np
import umap


def umap_embed(events_by_batch: dict, marker_idx: list,
               subsample: int = 30000, seed: int = 42) -> list:
    """Embed pooled batch events to 2D.

    Pools marker columns across all batches, subsamples down to ``subsample``
    total points, then fits a 2D UMAP.

    Returns [[x, y, batch_label], ...].
    """
    rng = np.random.default_rng(seed)
    marker_idx = list(marker_idx)

    pooled = []
    labels = []
    for label, ev in events_by_batch.items():
        ev = np.asarray(ev)
        pooled.append(ev[:, marker_idx])
        labels.extend([label] * ev.shape[0])

    if not pooled:
        return []

    X = np.vstack(pooled).astype(np.float32)
    labels = np.asarray(labels)

    n = X.shape[0]
    if n > subsample:
        sel = rng.choice(n, size=subsample, replace=False)
        X = X[sel]
        labels = labels[sel]

    reducer = umap.UMAP(n_components=2, random_state=seed)
    emb = reducer.fit_transform(X)

    out = []
    for (x, y), lab in zip(emb, labels):
        out.append([float(x), float(y), str(lab)])
    return out
