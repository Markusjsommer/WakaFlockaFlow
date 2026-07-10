"""Explainable gating paths for clustered populations (HyperFinder-style).

An unsupervised metacluster is defined over many markers at once, which is not
how a cytometrist gates. For each population we fit a shallow one-vs-rest
decision tree on the transformed marker matrix and read the root-to-leaf path as
a short sequence of marker-threshold gates that reproduces the cluster. We report
how faithful the reconstruction is (precision / recall / F1), so the gating path
is a defensible explanation rather than a black box, and can be exported to
FlowJo as real marker gates.
"""
from __future__ import annotations

import numpy as np

_NEG_INF = float("-inf")
_POS_INF = float("inf")


def _leaf_paths(tree):
    """Map each leaf node id -> list of (feature, threshold, go_left) along its path."""
    left, right = tree.children_left, tree.children_right
    feat, thr = tree.feature, tree.threshold
    paths: dict[int, list] = {}

    stack = [(0, [])]
    while stack:
        node, constraints = stack.pop()
        if left[node] == right[node]:  # leaf
            paths[node] = constraints
            continue
        f, t = int(feat[node]), float(thr[node])
        stack.append((left[node], constraints + [(f, t, True)]))   # X[f] <= t
        stack.append((right[node], constraints + [(f, t, False)]))  # X[f] >  t
    return paths


def _merge_constraints(path):
    """Collapse a leaf path into per-feature [lo, hi] intervals, order preserved."""
    order = []
    bounds: dict[int, list] = {}
    for f, t, go_left in path:
        if f not in bounds:
            bounds[f] = [_NEG_INF, _POS_INF]
            order.append(f)
        lo, hi = bounds[f]
        if go_left:      # X[f] <= t  -> upper bound
            bounds[f][1] = min(hi, t)
        else:            # X[f] >  t  -> lower bound
            bounds[f][0] = max(lo, t)
    return [(f, bounds[f][0], bounds[f][1]) for f in order]


def _apply(X, constraints):
    mask = np.ones(X.shape[0], dtype=bool)
    for f, lo, hi in constraints:
        if lo != _NEG_INF:
            mask &= X[:, f] > lo
        if hi != _POS_INF:
            mask &= X[:, f] <= hi
    return mask


def derive_gate_paths(X, labels, marker_names, metacluster_ids=None,
                      max_depth: int = 4, seed: int = 42, max_fit: int = 20000,
                      n_bins: int = 30) -> dict:
    """Derive a gating path per population.

    Returns {metacluster_id: {
        "steps": [{"marker","index","lo","hi","axis_min","axis_max","hist"}],
        "precision","recall","f1","coverage"}}.
    ``lo``/``hi`` are None when that side is open. ``hist`` = {"edges","target",
    "background"} for a 1-D biaxial view of that marker.
    """
    from sklearn.tree import DecisionTreeClassifier

    X = np.asarray(X, dtype=np.float32)
    labels = np.asarray(labels).astype(int)
    n, M = X.shape
    if metacluster_ids is None:
        metacluster_ids = sorted(np.unique(labels).tolist())

    axis_min = X.min(axis=0)
    axis_max = X.max(axis=0)

    rng = np.random.default_rng(seed)
    fit_idx = (np.sort(rng.choice(n, size=max_fit, replace=False))
               if n > max_fit else np.arange(n))
    Xf = X[fit_idx]

    out: dict[int, dict] = {}
    for mc in metacluster_ids:
        y_full = (labels == mc)
        if y_full.sum() == 0:
            continue
        yf = y_full[fit_idx].astype(int)
        if yf.sum() == 0 or yf.sum() == len(yf):
            continue

        clf = DecisionTreeClassifier(
            max_depth=max_depth, class_weight="balanced", random_state=seed
        ).fit(Xf, yf)
        tree = clf.tree_

        # Choose the positive-predicted leaf capturing the most target cells.
        paths = _leaf_paths(tree)
        best_leaf, best_cov = None, -1.0
        for leaf, path in paths.items():
            value = tree.value[leaf][0]  # [n_neg_weighted, n_pos_weighted]
            if value[1] <= value[0]:
                continue  # leaf predicts "rest"
            if value[1] > best_cov:
                best_cov = value[1]
                best_leaf = leaf
        if best_leaf is None:
            continue

        constraints = _merge_constraints(paths[best_leaf])
        pred = _apply(X, constraints)
        tp = int(np.sum(pred & y_full))
        fp = int(np.sum(pred & ~y_full))
        fn = int(np.sum(~pred & y_full))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

        steps = []
        for f, lo, hi in constraints:
            edges = np.linspace(float(axis_min[f]), float(axis_max[f]), n_bins + 1)
            tgt, _ = np.histogram(X[y_full, f], bins=edges)
            bg, _ = np.histogram(X[~y_full, f], bins=edges)
            steps.append({
                "marker": marker_names[f],
                "index": int(f),
                "lo": None if lo == _NEG_INF else float(lo),
                "hi": None if hi == _POS_INF else float(hi),
                "axis_min": float(axis_min[f]),
                "axis_max": float(axis_max[f]),
                "hist": {
                    "edges": [float(e) for e in edges],
                    "target": [int(v) for v in tgt],
                    "background": [int(v) for v in bg],
                },
            })

        out[int(mc)] = {
            "steps": steps,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "coverage": int(y_full.sum()),
        }
    return out
